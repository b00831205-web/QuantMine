"""Portfolio-state transitions shared by position-based backtest engines."""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Real

import pandas as pd

from ..plugins.context import SourceContext
from ..plugins.market_rules import (
    MarketRulesComponent,
    MarketStateProvider,
    TradeConstraintRequest,
    TradeConstraintResult,
    apply_market_rules_component,
    load_market_state_frame,
)


def _validate_numeric_series(
        value: object,
        *,
        name: str
) -> pd.Series:
    if not isinstance(value, pd.Series):
        raise TypeError(f"{name} must be a pandas Series")

    if not value.index.is_unique:
        raise ValueError(f"{name} index must be unique")

    if not pd.api.types.is_numeric_dtype(value.dtype):
        raise TypeError(f"{name} must contain numeric values")

    if value.isna().any():
        raise ValueError(f"{name} must not contain missing values")

    return value

@dataclass(frozen=True)
class PortfolioState:
    """Cash and long-only position immediately before or after a rebalance."""

    positions: pd.Series
    sellable_positions: pd.Series
    cash: float

    def __post_init__(self) -> None:
        positions = _validate_numeric_series(
            self.positions,
            name = "positions"
        )
        sellable_positions = _validate_numeric_series(
            self.sellable_positions,
            name = "sellable_positions"
        )
        if not self.sellable_positions.index.equals(positions.index):
            raise ValueError(
                "sellable_positions index must match positions index"
            )

        if (positions < 0).any():
            raise ValueError("positions must be non-negative")

        if (self.sellable_positions < 0).any():
            raise ValueError(
                "sellable_positions must be non-negative"
            )

        if (sellable_positions > positions).any():
            raise ValueError(
                "sellable_positions must not exceed positions"
            )

        if isinstance(self.cash, bool) or not isinstance(self.cash, Real):
            raise TypeError("cash must be a real number")

        if pd.isna(self.cash) or self.cash < 0:
            raise ValueError("cash must be non-negative")

    def start_next_session(self) -> PortfolioState:
        """Make every existing position sellable on the next trading day"""

        return PortfolioState(
            positions = self.positions.copy(),
            sellable_positions=self.positions.copy(),
            cash = float(self.cash)
        )

@dataclass(frozen=True)
class RebalanceExecutionResult:
    """One constrained portfolio transition"""

    state: PortfolioState
    requested_shares: pd.Series
    constraints: TradeConstraintResult
    equity_before: float
    equity_after: float

    def __post_init__(self) -> None:
        if not isinstance(self.state, PortfolioState):
            raise TypeError("state must be a PortfolioState")

        _validate_numeric_series(
            self.requested_shares,
            name="requested_shares",
        )

        if not isinstance(self.constraints, TradeConstraintResult):
            raise TypeError(
                "constraints must be a TradeConstraintResult"
            )

        for name, value in (
            ("equity_before", self.equity_before),
            ("equity_after", self.equity_after)
        ):
            if isinstance(value, bool) or not isinstance(value, Real):
                raise TypeError(f"{name} must be a real number")

            if pd.isna(value) or value < 0:
                raise ValueError(f"{name} must be non-negative")

def execute_target_weights(
        *,
        component: MarketRulesComponent,
        context: SourceContext,
        trade_date: pd.Timestamp,
        target_weights: pd.Series,
        prices: pd.Series,
        state: PortfolioState,
        market_state_provider: MarketStateProvider | None = None,
        tradable: pd.Series | None = None,
) -> RebalanceExecutionResult:
    """Convert target weights into orders and apply market-specific rules."""

    weights = _validate_numeric_series(
        target_weights,
        name = "target_weights"
    )
    current_prices = _validate_numeric_series(
        prices,
        name="prices"
    )

    expected_index = state.positions.index
    if not weights.index.equals(expected_index):
        raise ValueError(
            "target_weights index must match portfolio positions index"
        )

    if not current_prices.index.equals(expected_index):
        raise ValueError(
            "prices index must match portfolio positions index"
        )

    if tradable is None:
        active_tradable = pd.Series(True, index= expected_index.copy(), dtype=bool)

    else:
        if not isinstance(tradable, pd.Series):
            raise TypeError("tradable must be a pandas Series")

        if not pd.api.types.is_bool_dtype(tradable.dtype):
            raise TypeError("tradable must contain boolean values")

        if tradable.isna().any():
            raise ValueError("tradable must not contain missing values")

        if not tradable.index.equals(expected_index):
            raise ValueError("tradable index must match portofolio positions index")

        active_tradable = tradable

    if (weights < 0).any():
        raise ValueError(
            "target_weights must be non-negative"
        )

    if float(weights.sum()) > 1.0 + 1e-12:
        raise ValueError("target_weights must not sum above one")

    if (current_prices <= 0).any():
        raise ValueError("prices must contain positive values")

    equity_before = float(
        state.cash + (state.positions.astype(float) * current_prices).sum()
    )

    target_positions = (
        weights.astype(float) * equity_before / current_prices
    )

    requested_shares = (target_positions - state.positions.astype(float))
    requested_shares = requested_shares.where(requested_shares.abs() > 1e-12, 0.0)

    rule_requested_shares = requested_shares.where(active_tradable, 0.0)

    if market_state_provider is None:
        market_state = pd.DataFrame(index=expected_index.copy())
        market_state.index.name = "ticker"

    else:
        market_state = load_market_state_frame(market_state_provider, trade_date= trade_date, tickers = expected_index.tolist())

    constraint_request = TradeConstraintRequest(
        trade_date = trade_date,
        requested_shares = rule_requested_shares,
        prices = current_prices,
        positions = state.positions,
        sellable_positions = state.sellable_positions,
        cash = float(state.cash),
        market_state = market_state,
        metadata = {"target_weights": weights.to_dict(), "equity_before": equity_before, "tradable": active_tradable.to_dict()}
    )

    constraints = apply_market_rules_component(component, constraint_request, context)

    price_blocked = (~active_tradable & requested_shares.ne(0.0))
    if price_blocked.any():
        reasons = constraints.reasons.copy()
        reasons.loc[price_blocked] = "price_unavailable"
        constraints = TradeConstraintResult(
            executable_shares = constraints.executable_shares,
            fees = constraints.fees,
            reasons = reasons,
            metadata={
                **dict(constraints.metadata),
                "price_unavailable_tickers":(
                    requested_shares.index[price_blocked].tolist()
                )
            }
        )
    executable_shares = constraints.executable_shares.astype(float)
    fees = constraints.fees.astype(float)

    positions_after = state.positions.astype(float)+executable_shares
    sellable_after = state.sellable_positions.astype(float) + executable_shares.clip(upper=0.0)

    positions_after = positions_after.where(
        positions_after.abs() > 1e-12, 0.0
    )
    sellable_after = sellable_after.where(
        sellable_after.abs() > 1e-12, 0.0
    )
    cash_after = float(state.cash - (executable_shares * current_prices).sum() - fees.sum())
    if cash_after < -1e-8:
        raise ValueError("market-rules result would produce negative cash")

    if (positions_after < -1e-8).any():
        raise ValueError("market-rules result would produce a short position")

    if (sellable_after < -1e-8).any():
        raise ValueError("market-rules result sold more than the sellable position")

    cash_after = max(cash_after, 0.0)
    positions_after = positions_after.clip(lower=0.0)
    sellable_after = sellable_after.clip(lower=0.0)
    next_state = PortfolioState(positions = positions_after, sellable_positions= sellable_after, cash = cash_after)
    equity_after = float(cash_after + (positions_after * current_prices).sum())

    return RebalanceExecutionResult(
        state = next_state,
        requested_shares = requested_shares,
        constraints= constraints,
        equity_before= equity_before,
        equity_after= equity_after
    )
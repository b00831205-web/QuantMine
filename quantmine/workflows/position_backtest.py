"""Multi-session position backtesting over prepared target weights."""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Real

import pandas as pd

from ..plugins.context import SourceContext
from ..plugins.market_rules import MarketRulesComponent, MarketStateProvider
from .portfolio_execution import PortfolioState, execute_target_weights
from .price_resolution import LastObservationPricePolicy, PriceResolutionRequest, PriceResolutionPolicy


@dataclass(frozen=True)
class PositionBacktestResult:
    """Daily portfolio state and constrained rebalance history."""

    equity_curve: pd.Series
    daily_returns: pd.Series
    cash_curve: pd.Series
    positions: pd.DataFrame
    sellable_positions: pd.DataFrame
    requested_shares: pd.DataFrame
    executed_shares: pd.DataFrame
    fees: pd.DataFrame
    reasons: pd.DataFrame
    final_state: PortfolioState
    valuation_prices: pd.DataFrame
    tradable: pd.DataFrame
    price_sources: pd.DataFrame

    def __post_init__(self) -> None:
        if not isinstance(self.equity_curve, pd.Series):
            raise TypeError("equity_curve must be a pandas Series")

        if not isinstance(self.daily_returns, pd.Series):
            raise TypeError("daily_returns must be a pandas Series")

        if not isinstance(self.cash_curve, pd.Series):
            raise TypeError("cash_curve must be pandas Series")

        for name, frame in (
            ("positions", self.positions),
            ("sellable_positions", self.sellable_positions),
            ("requested_shares", self.requested_shares),
            ("executed_shares", self.executed_shares),
            ("fees", self.fees),
            ("reasons", self.reasons)
        ):
            if not isinstance(frame, pd.DataFrame):
                raise TypeError(f"{name} must be a pandas DataFrame")

        if not isinstance(self.final_state, PortfolioState):
            raise TypeError("final_state must be a PortfolioState")

        if not isinstance(self.valuation_prices, pd.DataFrame):
            raise TypeError("valuation_prices must be a pandas DataFrame")

        if not isinstance(self.tradable, pd.DataFrame):
            raise TypeError("tradable must be a pandas DataFrame")

        if not isinstance(self.price_sources, pd.DataFrame):
            raise TypeError("price_sources must be a pandas DataFrame")

def _validate_price_frame(close: object) -> pd.DataFrame:
    if not isinstance(close, pd.DataFrame):
        raise TypeError("close must be a pandas DataFrame")

    if close.empty:
        raise ValueError("close must not be empty")

    if not isinstance(close.index, pd.DatetimeIndex):
        raise TypeError("close index must be a DatetimeIndex")

    if close.index.has_duplicates:
        raise ValueError("close index must not contain duplicate dates")

    if not close.index.is_monotonic_increasing:
        raise ValueError("close index must be sorted")

    if close.columns.has_duplicates:
        raise ValueError("close columns must not contain duplicate tickers")

    if not all(pd.api.types.is_numeric_dtype(dtype) for dtype in close.dtypes):
        raise TypeError("close must contain numeric value")

    invalid_prices = close.notna() & (close<=0)
    if invalid_prices.any().any():
        raise ValueError("close must contain positive non-missing values")

    return close

def _validate_target_weights(target_weights: object, *, close: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(target_weights, pd.DataFrame):
        raise TypeError("target_weights must be a pandas DataFrame")

    if not isinstance(target_weights.index, pd.DatetimeIndex):
        raise TypeError("target_weights index must be a DatetimeIndex")

    if target_weights.index.has_duplicates:
        raise ValueError("target_weights index must not contain duplicate dates")

    if not target_weights.index.is_monotonic_increasing:
        raise ValueError("target_weights index must be sorted")

    if not target_weights.columns.equals(close.columns):
        raise ValueError("target_weights columns must match close columns")

    unknown_dates = target_weights.index.difference(close.index)
    if not unknown_dates.empty:
        raise ValueError(f"target_weights contains dates unavailable in close: {unknown_dates.tolist()}")

    if target_weights.isna().any().any():
        raise ValueError("target_weights must not contain missing values")

    if not all(pd.api.types.is_numeric_dtype(dtype) for dtype in target_weights.dtypes):
        raise TypeError("target_weights must contain numeric values")

    if (target_weights < 0).any().any():
        raise ValueError("target_weights must be non-negative")

    weight_sums = target_weights.sum(axis=1)
    if (weight_sums > 1.0 + 1e-12).any():
        raise ValueError("target_weights rows must not sum above one")

    return target_weights


def run_position_backtest(
        *,
        close: pd.DataFrame,
        target_weights: pd.DataFrame,
        initial_cash: float,
        component: MarketRulesComponent,
        context: SourceContext,
        market_state_provider: MarketStateProvider | None = None,
        initial_state: PortfolioState | None = None,
        price_policy: PriceResolutionPolicy | None = None
) -> PositionBacktestResult:
    """Run daily valuation and constrained trades on rebalance dates."""

    prices = _validate_price_frame(close)
    weights = _validate_target_weights(
        target_weights,
        close = prices
    )

    if isinstance(initial_cash, bool) or not isinstance(initial_cash, Real):
        raise TypeError("initial cash must be a real number")

    if pd.isna(initial_cash) or initial_cash <0:
        raise ValueError("initial_cash must be non-negative")

    tickers = prices.columns
    if initial_state is None:
        zero_positions = pd.Series(0.0, index= tickers.copy(),dtype = float)

        state = PortfolioState(positions = zero_positions.copy(), sellable_positions = zero_positions.copy(), cash = float(initial_cash))

    else:
        if not isinstance(initial_state, PortfolioState):
            raise TypeError("initial_state must be a PortfolioState")

        if not initial_state.positions.index.equals(tickers):
            raise ValueError("initial_state index must match close columns")

        state = initial_state

    active_price_policy = (
        price_policy if price_policy is not None else LastObservationPricePolicy()
    )

    if not isinstance(active_price_policy, PriceResolutionPolicy):
        raise TypeError("price_policy must implement PriceResolutionPolicy")

    last_prices = pd.Series(float("nan"), index=tickers.copy(), dtype=float)

    equity_values: dict[pd.Timestamp, float] = {}
    cash_values: dict[pd.Timestamp, float] = {}
    position_rows: dict[pd.Timestamp, pd.Series] = {}
    sellable_rows: dict[pd.Timestamp, pd.Series] = {}
    valuation_price_rows: dict[pd.Timestamp, pd.Series] = {}
    tradable_rows: dict[pd.Timestamp, pd.Series] = {}
    price_source_rows: dict[pd.Timestamp, pd.Series] = {}

    requested_shares = pd.DataFrame(0.0, index=weights.index.copy(), columns=tickers.copy())
    executed_shares = requested_shares.copy()
    fees = requested_shares.copy()
    reasons = pd.DataFrame("", index=weights.index.copy(), columns=tickers.copy(), dtype="object")

    for session_number, trade_date in enumerate(prices.index):
        if session_number > 0:
            state = state.start_next_session()

        raw_prices = prices.loc[trade_date]
        resolved_prices = active_price_policy.resolve(
            PriceResolutionRequest(
                trade_date = trade_date,
                raw_prices  = raw_prices,
                last_prices = last_prices,
                positions = state.positions,
            )
        )

        current_prices = resolved_prices.valuation_prices
        last_prices = raw_prices.combine_first(last_prices)

        if trade_date in weights.index:
            execution = execute_target_weights(
                component = component,
                context = context,
                trade_date = trade_date,
                target_weights= weights.loc[trade_date],
                prices = current_prices,
                state=state,
                market_state_provider = market_state_provider,
                tradable = resolved_prices.tradable
            )
            state = execution.state

            requested_shares.loc[trade_date] = execution.requested_shares
            executed_shares.loc[trade_date] = execution.constraints.executable_shares
            fees.loc[trade_date] = execution.constraints.fees
            reasons.loc[trade_date] = execution.constraints.reasons
        valuation_price_rows[trade_date] = resolved_prices.valuation_prices.copy()
        tradable_rows[trade_date] = resolved_prices.tradable.copy()
        price_source_rows[trade_date] = resolved_prices.sources.copy()

        equity = float(
            state.cash + (state.positions.astype(float) * current_prices).sum()
        )
        equity_values[trade_date] = equity
        cash_values[trade_date] = float(state.cash)
        position_rows[trade_date] = state.positions.copy()
        sellable_rows[trade_date] = state.sellable_positions.copy()

    equity_curve = pd.Series(equity_values, name="equity", dtype=float)
    equity_curve.index.name="date"
    cash_curve = pd.Series(cash_values, name="cash", dtype=float)
    cash_curve.index.name="date"

    positions = pd.DataFrame.from_dict(position_rows, orient="index").reindex(columns=tickers)
    positions.index.name = "date"
    sellable_positions = pd.DataFrame.from_dict(sellable_rows, orient="index").reindex(columns=tickers)
    sellable_positions.index.name="date"

    daily_returns = equity_curve.pct_change()
    daily_returns.name = "return"

    requested_shares.index.name = "date"
    executed_shares.index.name = "date"
    fees.index.name = "date"
    reasons.index.name = "date"

    valuation_prices = pd.DataFrame.from_dict(
        valuation_price_rows,
        orient="index"
    ).reindex(columns=tickers)
    valuation_prices.index.name = "date"

    tradable = pd.DataFrame.from_dict(
        tradable_rows,
        orient="index",
    ).reindex(columns=tickers)
    tradable.index.name = "date"

    price_sources = pd.DataFrame.from_dict(
        price_source_rows,
        orient="index"
    ).reindex(columns=tickers)
    price_sources.index.name="date"

    return PositionBacktestResult(
        equity_curve= equity_curve,
        daily_returns= daily_returns,
        cash_curve= cash_curve,
        positions= positions,
        sellable_positions= sellable_positions,
        requested_shares= requested_shares,
        executed_shares= executed_shares,
        fees = fees,
        reasons = reasons,
        final_state = state,
        valuation_prices= valuation_prices,
        tradable= tradable,
        price_sources= price_sources,
    )
"""Replaceable market-specific trade constraint contracts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from numbers import Real
from typing import Any, Protocol, runtime_checkable

import pandas as pd

from .context import SourceContext
from .contracts import PluginSpec
from .loader import resolve_plugin


def _validate_series(
    value: object,
    *,
    name: str,
    require_numeric: bool = True,
) -> pd.Series:
    if not isinstance(value, pd.Series):
        raise TypeError(f"{name} must be a pandas Series")

    if not value.index.is_unique:
        raise ValueError(f"{name} index must be unique")

    if require_numeric and not pd.api.types.is_numeric_dtype(value.dtype):
        raise TypeError(f"{name} must contain numeric values")

    return value


def _require_same_index(
    expected: pd.Index,
    value: pd.Series,
    *,
    name: str,
) -> None:
    if not value.index.equals(expected):
        raise ValueError(
            f"{name} index must match requested_shares index"
        )

@runtime_checkable
class MarketStateProvider(Protocol):
    """Provide point-in-time execution status for one security"""

    def status_on(
            self,
            trade_date: pd.Timestamp,
            ticker: str
    ) -> Mapping[str, object]:
        ...


@dataclass(frozen=True)
class TradeConstraintRequest:
    """Orders and portfolio state presented to a market-rules plugin."""

    trade_date: pd.Timestamp
    requested_shares: pd.Series
    prices: pd.Series
    positions: pd.Series
    sellable_positions: pd.Series
    cash: float
    market_state: pd.DataFrame
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.trade_date, pd.Timestamp):
            raise TypeError("trade_date must be a pandas Timestamp")

        if pd.isna(self.trade_date):
            raise ValueError("trade_date must not be NaT")

        requested_shares = _validate_series(
            self.requested_shares,
            name="requested_shares",
        )
        prices = _validate_series(
            self.prices,
            name="prices",
        )
        positions = _validate_series(
            self.positions,
            name="positions",
        )
        sellable_positions = _validate_series(
            self.sellable_positions,
            name="sellable_positions",
        )

        expected_index = requested_shares.index
        _require_same_index(expected_index, prices, name="prices")
        _require_same_index(expected_index, positions, name="positions")
        _require_same_index(
            expected_index,
            sellable_positions,
            name="sellable_positions",
        )

        if prices.isna().any() or (prices <= 0).any():
            raise ValueError("prices must contain positive values")

        if positions.isna().any() or (positions < 0).any():
            raise ValueError(
                "positions must contain non-negative values"
            )

        if (
            sellable_positions.isna().any()
            or (sellable_positions < 0).any()
        ):
            raise ValueError(
                "sellable_positions must contain non-negative values"
            )

        if (sellable_positions > positions).any():
            raise ValueError(
                "sellable_positions must not exceed positions"
            )

        if (
            isinstance(self.cash, bool)
            or not isinstance(self.cash, Real)
        ):
            raise TypeError("cash must be a real number")

        if pd.isna(self.cash) or self.cash < 0:
            raise ValueError("cash must be non-negative")

        if not isinstance(self.market_state, pd.DataFrame):
            raise TypeError("market_state must be a pandas DataFrame")

        if not self.market_state.index.is_unique:
            raise ValueError("market_state index must be unique")

        missing_tickers = expected_index.difference(
            self.market_state.index
        )
        if not missing_tickers.empty:
            raise ValueError(
                "market_state does not cover requested tickers: "
                f"{missing_tickers.tolist()}"
            )

        if not isinstance(self.metadata, Mapping):
            raise TypeError("metadata must be a mapping")


@dataclass(frozen=True)
class TradeConstraintResult:
    """Executable orders returned by a market-rules plugin."""

    executable_shares: pd.Series
    fees: pd.Series
    reasons: pd.Series
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        executable_shares = _validate_series(
            self.executable_shares,
            name="executable_shares",
        )
        fees = _validate_series(
            self.fees,
            name="fees",
        )
        reasons = _validate_series(
            self.reasons,
            name="reasons",
            require_numeric=False,
        )

        expected_index = executable_shares.index
        if not fees.index.equals(expected_index):
            raise ValueError(
                "fees index must match executable_shares index"
            )

        if not reasons.index.equals(expected_index):
            raise ValueError(
                "reasons index must match executable_shares index"
            )

        if not isinstance(self.metadata, Mapping):
            raise TypeError("metadata must be a mapping")


@runtime_checkable
class MarketRulesPlugin(Protocol):
    """Interface implemented by market-specific execution rules."""

    def apply(
        self,
        request: TradeConstraintRequest,
        context: SourceContext,
    ) -> TradeConstraintResult:
        ...


@dataclass(frozen=True)
class MarketRulesComponent:
    """Configured market-rules plugin and its dependencies."""

    id: str
    plugin: MarketRulesPlugin
    market: str
    connection_ref: str | None = None
    requires_connection: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.id, str)
            or not self.id
            or self.id.strip() != self.id
        ):
            raise ValueError(
                "market-rules component id must be a non-empty "
                "trimmed string"
            )

        if not isinstance(self.plugin, MarketRulesPlugin):
            raise TypeError(
                "plugin must implement MarketRulesPlugin"
            )

        if (
            not isinstance(self.market, str)
            or not self.market
            or self.market.strip() != self.market
        ):
            raise ValueError(
                "market must be a non-empty trimmed string"
            )

        if self.connection_ref is not None and (
            not isinstance(self.connection_ref, str)
            or not self.connection_ref
            or self.connection_ref.strip() != self.connection_ref
        ):
            raise ValueError(
                "connection_ref must be a non-empty trimmed string"
            )

        if not isinstance(self.requires_connection, bool):
            raise TypeError("requires_connection must be a bool")

        if self.requires_connection and self.connection_ref is None:
            raise ValueError(
                "connection_ref is required when "
                "requires_connection is true"
            )

        if not isinstance(self.metadata, Mapping):
            raise TypeError("metadata must be a mapping")

def apply_market_rules_component(
    component: MarketRulesComponent,
    request: TradeConstraintRequest,
    context: SourceContext,
) -> TradeConstraintResult:
    """Apply market rules and validate the plugin's execution decision."""

    result = component.plugin.apply(request, context)

    if not isinstance(result, TradeConstraintResult):
        raise TypeError(
            f"market-rules component '{component.id}' returned {type(result).__name__}, expected TradeConstraintResult"
        )

    expected_index = request.requested_shares.index
    if not result.executable_shares.index.equals(expected_index):
        raise ValueError(
            f"market-rules component '{component.id}' returned an executable_shares index that does not match the request"
        )

    requested = request.requested_shares
    executable = result.executable_shares

    if executable.isna().any():
        raise ValueError(
            f"market-rules component '{component.id}' returned missing executable share quantities"
        )

    opposite_direction = (
        ((requested > 0) & (executable < 0)) | ((requested < 0) & (executable > 0)) | ((requested == 0) & (executable != 0))
    )
    if opposite_direction.any():
        tickers = executable.index[opposite_direction].tolist()
        raise ValueError(f"market-rules component '{component.id}' reversed the requested trade direction for ticker: {tickers}")

    exceeds_request = executable.abs() > requested.abs()
    if exceeds_request.any():
        tickers = executable.index[exceeds_request].tolist()
        raise ValueError(
            f"market-rules component '{component.id}' returned executable quantities exceeding the request for ticker: {tickers}"
        )

    if result.fees.isna().any() or (result.fees < 0).any():
        raise ValueError(
            f"market-rules component '{component.id}' returned invalid negative or missing fees"
        )

    return result

@dataclass(frozen=True)
class UnrestrictedMarketRulesPlugin:
    """Pass orders through without market-specific quantity restrictions"""

    commission_rate: float = 0.0

    def __post_init__(self) -> None:
        if isinstance(self.commission_rate, bool) or not isinstance(self.commission_rate, Real):
            raise TypeError("commission_rate must be a real number")

        if pd.isna(self.commission_rate) or self.commission_rate <0:
            raise ValueError("commission_rate must be non-negative")

    def apply(
            self,
            request: TradeConstraintRequest,
            context: SourceContext,
    ) -> TradeConstraintResult:
        del context

        executable_shares = request.requested_shares.copy()
        traded_notional = executable_shares.abs() * request.prices
        fees = traded_notional * float(self.commission_rate)

        reasons = pd.Series("accepted", index=executable_shares.index, dtype="object")
        reasons.loc[executable_shares == 0] = "no_order"

        return TradeConstraintResult(
            executable_shares= executable_shares,
            fees = fees,
            reasons = reasons,
            metadata = {
                "market_rules": "unrestricted",
                "commission_rate": float(self.commission_rate),
            }
        )

def create_unrestricted_market_rules(
        **params: Any
) -> MarketRulesComponent:
    """Create the default market-rules component."""

    supported = {"market", "commission_rate"}
    unexpected = sorted(set(params) - supported)
    if unexpected:
        raise ValueError(
            "unsupported unrestricted market-rules parameters: " + ", ".join(unexpected)
        )

    market = params.get("market", "GLOBAL")
    commission_rate = params.get("commission_rate", 0.0)

    return MarketRulesComponent(
        id = "unrestricted_market_rules",
        plugin = UnrestrictedMarketRulesPlugin(commission_rate= commission_rate),
        market = market,
        requires_connection= False,
        metadata={"model": "unrestricted", "commission_rate": float(commission_rate)}
    )

def resolve_market_rules_component(spec: PluginSpec, *, allowed_module_prefixes: Iterable[str] | None = ("quantmine",)) -> MarketRulesComponent:
    """Resolve and validate a configured market-rules factory"""

    component = resolve_plugin(spec, allowed_module_prefixes= allowed_module_prefixes)

    if not isinstance(component, MarketRulesComponent):
        raise TypeError(
            f"market-rules factory {spec.entry_point!r} returned {type(component).__name__}, expected MarketRulesComponent"
        )

    return component

_A_SHARE_MARKET_STATE_COLUMNS = frozenset(
    {
        "is_suspended",
        "is_limit_up",
        "is_limit_down"
    }
)

@dataclass(frozen=True)
class AStockMarketRulesPlugin:
    """A-share trading constraints and transaction-cost model."""

    lot_size: int = 100
    commission_rate: float = 0.0003
    minimum_commission: float = 5.0
    stamp_duty_rate: float = 0.0005
    transfer_fee_rate: float = 0.00001

    def __post_init__(self) -> None:
        if isinstance(self.lot_size, bool) or not isinstance(self.lot_size, int):
            raise TypeError("lot_size must be an integer")

        if self.lot_size <= 0:
            raise ValueError("lot_size must be positive")

        for name, value in (
            ("commission_rate", self.commission_rate),
            ("minimum_commission", self.minimum_commission),
            ("stamp_duty_rate", self.stamp_duty_rate),
            ("transfer_fee_rate", self.transfer_fee_rate)
        ):
            if isinstance(value, bool) or not isinstance(value, Real):
                raise TypeError(f"{name} must be a real number")

            if pd.isna(value) or value < 0:
                raise ValueError(f"{name} must be non-negative")

    def apply(
            self,
            request: TradeConstraintRequest,
            context: SourceContext,
    ) -> TradeConstraintResult:
        del context

        missing_columns = (
            _A_SHARE_MARKET_STATE_COLUMNS - set(request.market_state.columns)
        )
        if missing_columns:
            raise ValueError(
                "A-share market_state is missing required columns: " +", ".join(sorted(missing_columns))
            )

        state = request.market_state.reindex(
            request.requested_shares.index
        )

        for column in sorted(_A_SHARE_MARKET_STATE_COLUMNS):
            if state[column].isna().any():
                raise ValueError(
                    f"A-share market_state '{column}' contains missing values"
                )

            if not pd.api.types.is_bool_dtype(state[column].dtype):
                raise TypeError(
                    f"A-share market_state column '{column}' must contain boolean values"
                )

        return self._apply_rules(request, state)

    def _calculate_fees(
            self,
            executable_shares: pd.Series,
            price: pd.Series,
    ) -> pd.Series:
        """Calculate per-security A-share transaction costs"""

        traded_notional = (executable_shares.abs() * price.loc[executable_shares.index])
        has_trade = executable_shares != 0
        is_sell = executable_shares <0

        commission = pd.Series(0.0, index=executable_shares.index)
        commission.loc[has_trade] = (traded_notional.loc[has_trade] * float(self.commission_rate)).clip(lower=float(self.minimum_commission))

        stamp_duty = pd.Series(0.0, index=executable_shares.index)
        stamp_duty.loc[is_sell] = traded_notional.loc[is_sell] * float(self.stamp_duty_rate)
        transfer_fee = pd.Series(0.0, index = executable_shares.index)
        transfer_fee.loc[has_trade] = (traded_notional.loc[has_trade] * float(self.transfer_fee_rate))
        return commission + stamp_duty + transfer_fee

    def _apply_rules(
            self,
            request: TradeConstraintRequest,
            state: pd.DataFrame
    ) -> TradeConstraintResult:
        requested = request.requested_shares.astype(float)
        index = requested.index

        executable = pd.Series(0.0, index = index)
        reasons = pd.Series("no_order", index = index, dtype = "object")

        buy_requested = requested > 0
        sell_requested = requested < 0
        has_order = requested != 0

        suspended = state["is_suspended"]
        limit_up = state["is_limit_up"]
        limit_down = state["is_limit_down"]

        suspended_orders = has_order & suspended
        reasons.loc[suspended_orders] = "suspended"

        limit_up_buys = buy_requested & ~suspended & limit_up
        reasons.loc[limit_up_buys] = "limit_up"

        limit_down_sells = sell_requested & ~suspended & limit_down
        reasons.loc[limit_down_sells] = "limit_down"

        executable_buys = buy_requested &~suspended & ~limit_up

        if executable_buys.any():
            buy_quantity = requested.loc[executable_buys]
            rounded_buys = (buy_quantity // self.lot_size) * self.lot_size

            executable.loc[executable_buys] = rounded_buys

            exact_buys = rounded_buys == buy_quantity
            reasons.loc[rounded_buys.index[exact_buys]] = "accepted"
            reasons.loc[rounded_buys.index[~exact_buys]] = "lot_size_adjusted"

        executable_sells = sell_requested & ~suspended & ~limit_down
        
        if executable_sells.any():
            sell_demand = -requested.loc[executable_sells]
            sellable = request.sellable_positions.loc[executable_sells]
            positions = request.positions.loc[executable_sells]

            sell_capacity = pd.concat([sell_demand, sellable], axis =1).min(axis=1)

            full_liquidation = (sell_capacity == positions) & (sell_capacity > 0)

            rounded_sells = (sell_capacity // self.lot_size) * self.lot_size
            sell_quantity = rounded_sells.where(~full_liquidation, sell_capacity)

            executable.loc[executable_sells] = -sell_quantity

            capacity_limited = sell_capacity < sell_demand
            lot_adjusted = ((sell_quantity < sell_capacity) & ~full_liquidation)

            accepted = ~capacity_limited & ~lot_adjusted
            reasons.loc[sell_capacity.index[accepted]] = "accepted"

            reasons.loc[sell_quantity.index[capacity_limited & ~lot_adjusted]] = "sellable_limited"
            reasons.loc[sell_quantity.index[~capacity_limited & lot_adjusted]] = "lot_size_adjusted"

            reasons.loc[sell_quantity.index[capacity_limited & lot_adjusted]] = "sellable_and_lot_size_adjusted"

        executable, reasons, cash_after_trades = (
            self._fit_buys_to_cash(
                executable_shares= executable,
                prices = request.prices,
                starting_cash= float(request.cash),
                reasons = reasons,
            )
        )
        
        fees = self._calculate_fees(executable, request.prices)
        return TradeConstraintResult(
            executable_shares= executable,
            fees = fees,
            reasons = reasons,
            metadata= {
                "market_rules": "cn_a_share",
                "lot_size": self.lot_size,
                "fees_applied": True,
                "commission_rate": float(self.commission_rate),
                "minimum_commission": float(self.minimum_commission),
                "stamp_duty_rate": float(self.stamp_duty_rate),
                "transfer_fee_rate": float(self.transfer_fee_rate),
                "cash_before_trades": float(request.cash),
                "cash_after_trades": cash_after_trades,
            }
        )

    def _cash_after_trades(
            self,
            *,
            starting_cash: float,
            executable_shares: pd.Series,
            prices: pd.Series,
            fees: pd.Series
    ) -> float:
        buy_notional = (executable_shares.clip(lower=0) * prices.loc[executable_shares.index]).sum()

        sell_notional = (-executable_shares.clip(upper=0) * prices.loc[executable_shares.index]).sum()

        return float(starting_cash + sell_notional - buy_notional - fees.sum())

    def _fit_buys_to_cash(
            self,
            *,
            executable_shares: pd.Series,
            prices: pd.Series,
            starting_cash: float,
            reasons: pd.Series
    ) -> tuple[pd.Series, pd.Series, float]:
        """Scale buy orders propertionally until total cash remains valid"""

        executable = executable_shares.copy()
        adjusted_reasons = reasons.copy()

        initial_fees = self._calculate_fees(executable, prices)
        initial_cash_after = self._cash_after_trades(
            starting_cash= starting_cash,
            executable_shares= executable,
            prices = prices,
            fees = initial_fees,
        )

        if initial_cash_after >= -1e-9:
            return (executable, adjusted_reasons, max(initial_cash_after, 0.0))

        buy_mask = executable > 0
        if not buy_mask.any():
            return executable, adjusted_reasons, initial_cash_after

        sell_only = executable.where(executable <0, 0.0)
        sell_fees = self._calculate_fees(sell_only, prices)
        sell_proceeds = (-sell_only * prices.loc[sell_only.index]).sum()

        available_for_buys = float(starting_cash + sell_proceeds - sell_fees.sum())
        available_for_buys = max(available_for_buys, 0.0)

        requested_buys = executable.where(buy_mask, 0.0)
        best_buys = pd.Series(0.0, index= executable.index)

        lower = 0.0
        upper = 1.0

        for _ in range(60):
            scale = (lower+upper) /2.0
            scaled_buys = ((requested_buys * scale) // self.lot_size) * self.lot_size

            buy_fees = self._calculate_fees(scaled_buys , prices)
            buy_notional = (scaled_buys * prices.loc[scaled_buys.index]).sum()
            total_buy_cost = float(buy_notional + buy_fees.sum())

            if total_buy_cost <= available_for_buys + 1e-9:
                best_buys = scaled_buys
                lower = scale
            else:
                upper = scale
        executable.loc[buy_mask] = best_buys.loc[buy_mask]
        cash_limited = executable.loc[buy_mask] < executable_shares.loc[buy_mask]
        limited_tickers = cash_limited.index[cash_limited]
        adjusted_reasons.loc[limited_tickers] = "cash_limited"

        final_fees = self._calculate_fees(executable, prices)
        final_cash_after = self._cash_after_trades(
            starting_cash= starting_cash,
            executable_shares= executable,
            prices = prices,
            fees =final_fees
        )

        if final_cash_after < -1e-7:
            raise RuntimeError(
                f"A-share cash fitting produced negative cash: {final_cash_after}"
            )

        return (
            executable,
            adjusted_reasons,
            max(final_cash_after, 0.0)
        )

def create_a_stock_market_rules(**params: Any) -> MarketRulesComponent:
    """Create the configuration A-share market-rules component."""

    supported = {
        "market",
        "lot_size",
        "commission_rate",
        "minimum_commission",
        "stamp_duty_rate",
        "transfer_fee_rate"
    }
    unexpected = sorted(set(params) - supported)
    if unexpected:
        raise ValueError(
            "unsupported A-share market-rules parameters: "+ ", ".join(unexpected)
        )

    market = params.get("market", "CN")
    if market != "CN":
        raise ValueError("A-share market-rules factory requires market='CN'")

    plugin = AStockMarketRulesPlugin(
        lot_size=params.get("lot_size", 100),
        commission_rate = params.get("commission_rate", 0.0003),
        minimum_commission=params.get("minimum_commission", 5.0),
        stamp_duty_rate=params.get("stamp_duty_rate", 0.0005),
        transfer_fee_rate=params.get("transfer_fee_rate", 0.00001),
    )
    return MarketRulesComponent(
        id="cn_a_share_market_rules",
        plugin=plugin,
        market="CN",
        requires_connection=False,
        metadata={
            "model": "cn_a_share_cash_constrained",
            "lot_size": plugin.lot_size,
            "commission_rate": float(plugin.commission_rate),
            "minimum_commission": float(plugin.minimum_commission),
            "stamp_duty_rate": float(plugin.stamp_duty_rate),
            "transfer_fee_rate": float(plugin.transfer_fee_rate)
        }
    )

def load_market_state_frame(
        provider: MarketStateProvider,
        *,
        trade_date: pd.Timestamp,
        tickers: Iterable[str],
) -> pd.DataFrame:
    """Load ticker-indexed execution state without market-specific coupling."""

    if not isinstance(provider, MarketStateProvider):
        raise TypeError(
            "provider must implement MarketStateProvider"
        )

    if not isinstance(trade_date, pd.Timestamp):
        raise TypeError("trade_date must be a pandas Timestamp")

    if pd.isna(trade_date):
        raise ValueError("trade_date must not be NaT")

    ticker_list = list(tickers)
    for ticker in ticker_list:
        if not isinstance(ticker, str) or not ticker or ticker.strip() != ticker:
            raise ValueError("tickers must contain non-empty trimmed strings")

    if len(ticker_list) != len(set(ticker_list)):
        raise ValueError("tickers must not contain duplicates")

    rows: list[dict[str, object]] = []
    for ticker in ticker_list:
        status = provider.status_on(trade_date, ticker)
        if not isinstance(status, Mapping):
            raise TypeError(
                f"MarketStateProvider.status_on() must return a mapping for ticker {ticker!r}"
            )
        rows.append(dict(status))

    return pd.DataFrame(
        rows,
        index= pd.Index(ticker_list, name="ticker")
    )

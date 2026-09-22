"""Replaceable valuation and execution-price resolution policies"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import pandas as pd


def _validate_price_series(value: object, *, name: str, allow_missing: bool) -> pd.Series:
    if not isinstance(value, pd.Series):
        raise TypeError(f"{name} must be a pandas Series")

    if not value.index.is_unique:
        raise ValueError(f"{name} index mut be unique")

    if not pd.api.types.is_numeric_dtype(value.dtype):
        raise TypeError(f"{name} must contain numeric values")

    if not allow_missing and value.isna().any():
        raise ValueError(f"{name} must not contain missing values")

    non_missing = value.dropna()
    if (non_missing <= 0).any():
        raise ValueError(
            f"{name} must contain positive non-missing values"
        )
    return value

@dataclass(frozen=True)
class PriceResolutionRequest:
    """Raw and previously observed prices for on trading session."""

    trade_date: pd.Timestamp
    raw_prices: pd.Series
    last_prices: pd.Series
    positions: pd.Series

    def __post_init__(self) -> None:
        if not isinstance(self.trade_date, pd.Timestamp):
            raise TypeError("trade_date must be a pandas Timestamp")

        if pd.isna(self.trade_date):
            raise ValueError("trade_date must not be NaT")

        raw_prices = _validate_price_series(self.raw_prices, name="raw_prices", allow_missing=True)
        last_prices = _validate_price_series(self.last_prices, name="last_price", allow_missing= True)

        if not isinstance(self.positions, pd.Series):
            raise TypeError("positions must be a pandas Series")

        if not self.positions.index.is_unique:
            raise ValueError("positions index must be unique")

        if not pd.api.types.is_numeric_dtype(self.positions.dtype):
            raise TypeError("positions must contain numeric values")

        if self.positions.isna().any():
            raise ValueError("positions must not contain missing values")

        if (self.positions < 0).any():
            raise ValueError("positions must be non-negative")

        expected_index = raw_prices.index
        if not last_prices.index.equals(expected_index):
            raise ValueError("last_prices must match raw_prices index")

        if not self.positions.index.equals(expected_index):
            raise ValueError("positions index must match raw_prices index")

@dataclass(frozen=True)
class ResolvedPrices:
    """Valuation prices and current-session tradability"""

    valuation_prices: pd.Series
    tradable: pd.Series
    sources: pd.Series

    def __post_init__(self) -> None:
        valuation_prices = _validate_price_series(self.valuation_prices, name="valuation_prices", allow_missing= False)

        if not isinstance(self.tradable, pd.Series):
            raise TypeError("tradable must be a pandas Series")

        if not pd.api.types.is_bool_dtype(self.tradable.dtype):
            raise TypeError("tradable must contain boolean dtype")

        if self.tradable.isna().any():
            raise ValueError("tradable must not contain missing values")

        if not isinstance(self.sources, pd.Series):
            raise TypeError("sources must be a pandas Series")

        if self.sources.isna().any():
            raise ValueError("sources must not contain missing values")

        expected_index = valuation_prices.index
        if not self.tradable.index.equals(expected_index):
            raise ValueError("tradable index must match valuation_pirces index")

        if not self.sources.index.equals(expected_index):
            raise ValueError("sources index must match valuation_prices index")

@runtime_checkable
class PriceResolutionPolicy(Protocol):
    """Resolve safe valuation prices without inventing tradability"""

    def resolve(
            self,
            request: PriceResolutionRequest
    ) -> ResolvedPrices:
        ...


@dataclass(frozen=True)
class LastObservationPricePolicy:
    """Use the las observed price for valuation, never for execution"""

    flat_position_fallback: float = 1.0

    def __post_init__(self) -> None:
        if isinstance(self.flat_position_fallback, bool) or not isinstance(self.flat_position_fallback, (int, float)):
            raise TypeError("flat_position_fallback must be a real number")

        if pd.isna(self.flat_position_fallback) or self.flat_position_fallback <= 0:
            raise ValueError("flat_position_fallback must be positive")


    def resolve(self, request: PriceResolutionRequest) -> ResolvedPrices:
        raw_prices = request.raw_prices.astype(float)
        last_prices = request.last_prices.astype(float)

        tradable = raw_prices.notna()
        valuation_prices = raw_prices.copy()

        use_last = raw_prices.isna() & last_prices.notna()
        valuation_prices.loc[use_last] = last_prices.loc[use_last]

        still_unpriced = valuation_prices.isna()
        unpriced_positions = still_unpriced & (request.positions >0)
        if unpriced_positions.any():
            tickers = valuation_prices.index[unpriced_positions].tolist()
            raise ValueError(f"held positions have no current or historical valuation price: {tickers}")

        valuation_prices.loc[still_unpriced] = float(self.flat_position_fallback)

        sources = pd.Series("observed", index = valuation_prices.index, dtype="object")
        sources.loc[use_last] = "last_observation"
        sources.loc[still_unpriced] = "unavailable_flat"
        return ResolvedPrices(
            valuation_prices=valuation_prices,
            tradable=tradable.astype(bool),
            sources= sources,
        )
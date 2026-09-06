"""Built-in US-equity research plugin."""

from __future__ import annotations

from ..datareader import YFinanceSource
from .contracts import (
    DataSourceComponent,
    FactorPackComponent,
    MarketDataCapability,
    UniverseComponent,
)

from dataclasses import dataclass

import pandas as pd
from .eligibility import DailyEligibilityPolicy, DailyEligibilityUniverse


_US_ELIGIBILITY_COLUMNS = (
    "date",
    "ticker",
    "is_listed",
    "is_halted",
    "listing_days",
    "security_type",
    "is_adr"
)

def create_yfinance_data_source(**params: object) -> DataSourceComponent:
    return DataSourceComponent(
        id="yfinance",
        source=YFinanceSource(**params),
        capabilities=frozenset({
            MarketDataCapability.CLOSE,
            MarketDataCapability.VOLUME,
        }),
        metadata={
            "market": "US",
            "adjustment": "provider_default",
        },
    )


def create_sp500_universe() -> UniverseComponent:
    return UniverseComponent(
        id="sp500_membership",
        metadata={
            "index_name": "SP500",
            "benchmark_ticker": "SPY",
        },
    )


def create_us_technical_factor_pack() -> FactorPackComponent:
    from .. import factor_mining
    _ = factor_mining

    return FactorPackComponent(
        id="us_technical_v1",
        requires=frozenset({
            MarketDataCapability.CLOSE,
            MarketDataCapability.VOLUME,
        }),
        signals=(
            "momentum",
            "ShortTermReversal",
            "TwentyDayVolatility",
            "TwentyDayNegVotality",
            "TwentyDayAvgVol",
            "VolPriceCorr",
        ),
        metadata={
            "market": "US",
            "registry_module": "quantmine.factor_mining",
        },
    )

@dataclass(frozen=True)
class USEquityEligibilityPolicy:
    """US-specific rules translated into the generic daily eligibility model"""

    min_listing_days: int = 60
    exclude_halted: bool = True
    exclude_adrs: bool = True
    allowed_security_types: frozenset[str] = frozenset({"COMMON_STOCK"})

    def __post_init__(self) -> None:
        if self.min_listing_days < 0:
            raise ValueError("min_listing_days must be non-negative")

        normalized_types = frozenset(
            security_type.strip().upper()
            for security_type in self.allowed_security_types
            if security_type.strip()
        )
        if not normalized_types:
            raise ValueError("allowed_security_types cannot be empty")

        object.__setattr__(self, "allowed_security_types", normalized_types)

@dataclass(frozen = True)
class USEquityEligibilityUniverse:
    """US-market adapter over the shared point-in-time eligibility universe"""

    _universe: DailyEligibilityUniverse

    @classmethod
    def from_frame(
        cls,
        frame: pd.DataFrame,
        *,
        policy: USEquityEligibilityPolicy | None = None,
    ) -> "USEquityEligibilityUniverse":
        if not isinstance(frame, pd.DataFrame):
            raise TypeError("US eligibility data must be a DataFrame")

        missing = [
            column for column in _US_ELIGIBILITY_COLUMNS
            if column not in frame.columns
        ]
        if missing:
            raise ValueError(
                "US eligibility data is missing required columns: "
                + ", ".join(missing)
            )
        active_policy = policy or USEquityEligibilityPolicy()
        normalized = frame.loc[:, _US_ELIGIBILITY_COLUMNS].copy()

        for column in ("is_halted", "is_adr"):
            if normalized[column].isna().any():
                raise ValueError(
                    f"US eligibility data contains null {column!r}"
                )
            normalized[column] = normalized[column].astype(bool)

        normalized["security_type"] = (
            normalized["security_type"].astype(str).str.strip().str.upper()
        )
        if (normalized["security_type"] == "").any():
            raise ValueError("US eligibility data contains an empty security_type")

        normalized["is_tradable"] = True
        if active_policy.exclude_halted:
            normalized["is_tradable"] &= ~normalized["is_halted"]
        if active_policy.exclude_adrs:
            normalized["is_tradable"] &= ~normalized["is_adr"]

        normalized["is_tradable"] &= normalized["security_type"].isin(
            active_policy.allowed_security_types
        )
        return cls(
            _universe = DailyEligibilityUniverse.from_frame(
                normalized,
                policy = DailyEligibilityPolicy(
                    min_listing_days = active_policy.min_listing_days,
                    require_tradable = True
                ),
            )
        )

    def get_constituents(self, date: pd.Timestamp) -> set[str]:
        return self._universe.get_constituents(date)

    def status_on(
            self,
            date: pd.Timestamp,
            ticker: str,
    )-> dict[str, bool | str]:
        status = self._universe.status_on(date, ticker)
        if not status:
            normalized_date = pd.Timestamp(date).normalize()
            raise KeyError(
                f"No US eligibility status for {ticker!r} "
                f"no {normalized_date.date().isoformat()}"
            )

        return {
            "is_halted": bool(status["is_halted"]),
            "security_type": str(status["security_type"]),
            "is_adr": bool(status["is_adr"]),
        }
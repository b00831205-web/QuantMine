"""Normalize forward AkShare new snapshots into daily A-share status tables."""

from __future__ import annotations

from dataclasses import dataclass, field
import pandas as pd
from numbers import Real

from ..plugins.a_share import AStockSecurityMaster
from .market_status import DailyMarketStatus


_REQUIRED_SPOT_COLUMNS = ("代码", "名称", "最新价")
_REQUIRED_SUSPENSION_COLUMNS = ("代码", "名称", "停牌时间")
_LIMIT_PRICE_COLUMNS = ("涨停", "跌停")
_LIMIT_FLAG_COLUMNS = ("is_limit_up", "is_limit_down")


@dataclass(frozen = True)
class SpotCoveragePolicy:
    """Control how many active securities may be absent from a spot snapshot."""

    max_missing_count: int = 0
    max_missing_ratio: float = 0.0

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_missing_count, bool)
            or not isinstance(self.max_missing_count, int)
        ):
            raise TypeError("max_missing_count must be an integer")
        if self.max_missing_count < 0:
            raise ValueError("max_missing_count must be non-negative")

        if (
            isinstance(self.max_missing_ratio, bool)
            or not isinstance(self.max_missing_ratio, Real)
        ):
            raise TypeError("max_missing_ratio must be numeric")

        ratio = float(self.max_missing_ratio)
        if not 0.0 <= ratio <= 1.0:
            raise ValueError("max_missing_ratio must be between 0 and 1")

        object.__setattr__(self, "max_missing_ratio", ratio)

    def allows(
            self,
            *,
            missing_count: int,
            active_count: int,
    ) -> bool:
        missing_ratio = (
            missing_count / active_count if active_count else 0.0
        )
        return (
            missing_count <= self.max_missing_count and missing_ratio <= self.max_missing_ratio
        )


@dataclass(frozen = True)
class AStockDailyStatusNormalizer:
    """Derive standard daily status tables from an observed raw snapshot"""

    security_master: AStockSecurityMaster
    trading_calendar: pd.DatetimeIndex
    spot_coverage_policy: SpotCoveragePolicy = field(default_factory= SpotCoveragePolicy)

    def normalize(
            self,
            *,
            as_of_date: pd.Timestamp | str,
            spot: pd.DataFrame,
            suspension:pd.DataFrame,
    ) -> DailyMarketStatus:
        date = pd.Timestamp(as_of_date).normalize()
        master_status = self.security_master.status_on(
            date,
            trading_calendar = self.trading_calendar,
        )

        normalized_spot = self._normalize_spot(spot)
        noramlized_suspension = self._normalize_suspension(suspension)

        master_tickers = set(master_status["ticker"])
        spot_tickers = set(normalized_spot["ticker"])
        active_tickers = set(
            master_status.loc[master_status["is_listed"], "ticker"]
        )

        missing_active = sorted(active_tickers - spot_tickers)
        missing_ratio = (
            len(missing_active) / len(active_tickers) if active_tickers else 0.0
        )
        if missing_active and not self.spot_coverage_policy.allows(
            missing_count = len(missing_active),
            active_count= len(active_tickers),
        ):
            raise ValueError(
                "active master tickers missing from spot: "
                f"missing_count={len(missing_active)}, "
                f"active_count={len(active_tickers)}, "
                f"missing_ratio={missing_ratio:.6f}"
                +", ".join(missing_active)
            )

        unknown_spot = sorted(spot_tickers - master_tickers)
        if unknown_spot:
            raise ValueError(
                "spot snapshot contains tickers missing from security master: "
                +", ".join(unknown_spot) 
            )

        suspension_tickers = (set(noramlized_suspension["ticker"]) & master_tickers)


        spot_by_ticker = normalized_spot.set_index("ticker")

        status = master_status.loc[
            :,
            [
                "ticker",
                "is_listed",
                "listing_days",
                "listing_id",
                "exchange",
                "security_type",
            ],
        ].copy()
        status.insert(0, "date", date)

        status["is_source_missing"] = status["ticker"].isin(missing_active)
        status["is_suspended"] = status["ticker"].isin(suspension_tickers)
        status["is_tradable"] = (
            status["is_listed"]
            & ~status["is_suspended"]
            & ~status["is_source_missing"]
        )

        status["is_st"] = False
        observed_listed_mask = (
            status["is_listed"]
            & ~status["is_source_missing"]
        )
        observed_listed_tickers = status.loc[
            observed_listed_mask,
            "ticker",
        ]
        status.loc[observed_listed_mask, "is_st"] = [
            bool(spot_by_ticker.at[ticker, "is_st"])
            for ticker in observed_listed_tickers
        ]

        status["is_limit_up"] = False
        status["is_limit_down"] = False

        tradable_mask = status["is_tradable"]
        tradable_tickers = status.loc[tradable_mask, "ticker"]

        status.loc[tradable_mask, "is_limit_up"] = [
            bool(spot_by_ticker.at[ticker, "is_limit_up"])
            for ticker in tradable_tickers
        ]
        status.loc[tradable_mask, "is_limit_down"] = [
            bool(spot_by_ticker.at[ticker, "is_limit_down"])
            for ticker in tradable_tickers
        ]

        status = status.loc[
            :,
            [
                "date",
                "ticker",
                "is_listed",
                "is_tradable",
                "listing_days",
                "listing_id",
                "exchange",
                "security_type",
                "is_st",
                "is_suspended",
                "is_source_missing",
                "is_limit_up",
                "is_limit_down",
            ],
        ]

        return DailyMarketStatus.from_frame(status)

    @staticmethod
    def _normalize_spot(frame: pd.DataFrame) -> pd.DataFrame:
        AStockDailyStatusNormalizer._validate_frame(
            frame,
            required_columns = _REQUIRED_SPOT_COLUMNS,
            label = "spot snapshot"
        )

        has_limit_prices = all(
            column in frame.columns
            for column in _LIMIT_PRICE_COLUMNS
        )
        has_limit_flags = all(
            column in frame.columns
            for column in _LIMIT_FLAG_COLUMNS
        )

        if not has_limit_prices and not has_limit_flags:
            raise ValueError(
                "spot snapshot must provide a limit status representation: "
                "either 涨停/跌停 price or "
                "is_limit_up/is_limit_down flags"
            )

        limit_columns = (
            _LIMIT_PRICE_COLUMNS
            if has_limit_prices
            else _LIMIT_FLAG_COLUMNS
        )

        normalized = frame.loc[:, [*_REQUIRED_SPOT_COLUMNS, *limit_columns],].copy()
        normalized["ticker"] = (
            normalized.pop("代码").astype(str).str.strip().str.zfill(6)
        )
        if normalized["ticker"].duplicated().any():
            raise ValueError("spot snapshot contains duplicate tickers")

        names = normalized.pop("名称").astype(str).str.strip().str.upper()
        normalized["is_st"] = names.str.lstrip("*").str.startswith("ST")

        if has_limit_prices:
            for column in _LIMIT_PRICE_COLUMNS:
                normalized[column] = pd.to_numeric(
                    normalized[column],
                    errors = "raise"
                )

            normalized["最新价"] = pd.to_numeric(normalized["最新价"], errors = "raise")

            normalized["is_limit_up"] = (
                (normalized["最新价"] - normalized["涨停"]).abs()<=1e-8
            )
            normalized["is_limit_down"] = (
                (normalized["最新价"] - normalized["跌停"]).abs()<=1e-8
            )
        else:
            for column in _LIMIT_FLAG_COLUMNS:
                if normalized[column].isna().any():
                    raise ValueError(
                        f"spot snapshot contains null {column!r}"
                    )
                if not pd.api.types.is_bool_dtype(normalized[column]):
                    raise TypeError(
                        f"spot snapshot column {column!r} must be boolean"
                    )
                normalized[column] = normalized[column].astype(bool)

        return normalized

    @staticmethod
    def _normalize_suspension(frame: pd.DataFrame) -> pd.DataFrame:
        AStockDailyStatusNormalizer._validate_frame(
            frame, required_columns = _REQUIRED_SUSPENSION_COLUMNS, label = "suspension snapshot"
        )

        normalized = frame.loc[:, _REQUIRED_SUSPENSION_COLUMNS].copy()
        normalized["ticker"] = (
            normalized.pop("代码").astype(str).str.strip().str.zfill(6)
        )
        if normalized["ticker"].duplicated().any():
            raise ValueError("suspension snapshot contains duplicate tickers")

        return normalized

    @staticmethod
    def _validate_frame(
        frame: object,
        *,
        required_columns: tuple[str, ...],
        label: str,
    ) -> None:
        if not isinstance(frame, pd.DataFrame):
            raise TypeError(f"{label} must be a pandas DataFrame")

        missing = [
            column for column in required_columns if column not in frame.columns
        ]

        if missing:
            raise ValueError(
                f"{label} is missing required columns: "
                + ", ".join(missing)
            )

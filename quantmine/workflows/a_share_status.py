"""Normalize forward AkShare new snapshots into daily A-share status tables."""

from __future__ import annotations

from dataclasses import dataclass
import pandas as pd

from ..plugins.a_share import AStockSecurityMaster
from .market_status import DailyMarketStatus


_REQUIRED_SPOT_COLUMNS = ("代码", "名称", "最新价", "涨停", "跌停")
_REQUIRED_SUSPENSION_COLUMNS = ("代码", "名称", "停牌时间")


@dataclass(frozen = True)
class AStockDailyStatusNormalizer:
    """Derive standard daily status tables from an observed raw snapshot"""

    security_master: AStockSecurityMaster
    trading_calendar: pd.DatatimeIndex

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
        if missing_active:
            raise ValueError(
                "active master tickers missing from spot: "
                +", ".join(missing_active)
            )

        unknown_spot = sorted(spot_tickers - master_tickers)
        if unknown_spot:
            raise ValueError(
                "spot snapshot contains tickers missing from security master: "
                +", ".join(unknown_spot) 
            )

        suspension_tickers = set(noramlized_suspension["ticker"])
        unknown_suspension = sorted(suspension_tickers - master_tickers)
        if unknown_suspension:
            raise ValueError(
                "suspension snapshot contains tickers missing from security master: "
                +", ".join(unknown_suspension)
            )

        spot_by_ticker = normalized_spot.set_index("ticker")
        listed_mask = master_status["is_listed"]

        status = master_status.loc[:,[
            "ticker",
            "is_listed",
            "listing_days",
            "listing_id",
            "exchange",
            "security_type"
        ]].copy()
        status.insert(0, "date", date)

        status["is_suspended"] = status["ticker"].isin(suspension_tickers)
        status["is_tradable"] = (
            status["is_listed"] & ~status["is_suspended"]
        )

        status["is_st"] = False
        listed_tickers = status.loc[status["is_listed"], "ticker"]
        status.loc[status["is_listed"], "is_st"] =[
            bool(spot_by_ticker.at[ticker, "is_st"])
            for ticker in listed_tickers
        ]

        status["is_limit_up"] = False
        status["is_limit_down"] = False
        tradable_tickers = status.loc[status["is_tradable"],"ticker"]

        status.loc[status["is_tradable"], "is_limit_up"] = [
            bool(spot_by_ticker.at[ticker, "is_limit_up"])
            for ticker in tradable_tickers
        ]

        status.loc[status["is_tradable"], "is_limit_down"] = [
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
                "is_limit_up",
                "is_limit_down"
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

        normalized = frame.loc[:, _REQUIRED_SPOT_COLUMNS].copy()
        normalized["ticker"] = (
            normalized.pop("代码").astype(str).str.strip().str.zfill(6)
        )
        if normalized["ticker"].duplicated().any():
            raise ValueError("spot snapshot contains duplicate tickers")

        names = normalized.pop("名称").astype(str).str.strip().str.upper()
        normalized["is_st"] = names.str.lstrip("*").str.startswith("ST")

        for column in ("最新价","涨停","跌停"):
            normalized[column] = pd.to_numeric(
                normalized[column],
                errors = "raise",
            )
        normalized["is_limit_up"] = (
            (normalized["最新价"] - normalized["涨停"]).abs()<=1e-8
        )
        normalized["is_limit_down"] = (
            (normalized["最新价"] - normalized["跌停"]).abs()<=1e-8
        )

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
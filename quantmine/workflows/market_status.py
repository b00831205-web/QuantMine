"""Market-neutral daily status contract"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

_REQUIRED_COLUMNS = (
    "date",
    "ticker",
    "is_listed",
    "is_tradable",
    "listing_days"
)

@dataclass(frozen = True)
class DailyMarketStatus:
    """Validated daily market state with market-specific extension columns"""

    _frame: pd.DataFrame

    @classmethod
    def from_frame(cls, frame: pd.DataFrame) -> "DailyMarketStatus":
        if not isinstance(frame, pd.DataFrame):
            raise TypeError(
                "daily market status must be a pandas DataFrame"
            )

        missing = [
            column for column in _REQUIRED_COLUMNS
            if column not in frame.columns
        ]
        if missing:
            raise ValueError(
                "daily market status is missing required columns: "
                + ", ".join(missing)
            )

        normalized = frame.copy()
        normalized["date"] = pd.to_datetime(
            normalized["date"],
            errors = "raise",
        ).dt.normalize()

        if normalized["date"].isna().any():
            raise ValueError("daily market status must contain exactly one date")

        if normalized["date"].nunique()!=1:
            raise ValueError(
                "daily market status must contain exactly one date"
            )

        normalized["ticker"] = normalized["ticker"].astype(str).str.strip()
        if (normalized["ticker"] == "").any():
            raise ValueError(
                "daily market status ticker must not be empty"
            )

        if normalized["ticker"].duplicated().any():
            raise ValueError(
                "daily market status contains duplicate tickers"
            )

        for column in ("is_listed", "is_tradable"):
            if normalized[column].isna().any():
                raise ValueError(
                    f"daily market status {column} must not be null"
                )
            normalized[column] = normalized[column].astype(bool)

        normalized["listing_days"] = pd.to_numeric(
            normalized["listing_days"],
            errors = "raise"
        )

        if normalized["listing_days"].isna().any():
            raise ValueError(
                "daily market status listing_days must not be null"
            )
        if (normalized["listing_days"] < 0).any():
            raise ValueError(
                "daily market status listing_days must be non-negative"
            )

        return cls(_frame = normalized)

    @property
    def as_of_date(self) -> pd.Timestamp:
        return self._frame["date"].iloc[0]

    @property
    def frame(self) -> pd.DataFrame:
        """Return a copy so callers annot mutate the validated contract"""
        return self._frame.copy()
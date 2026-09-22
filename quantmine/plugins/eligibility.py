"""Market-neutral point-in-time eligibility universe primitives"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

import pandas as pd

_REQUIRED_COLUMNS = (
    "date",
    "ticker",
    "is_listed",
    "is_tradable",
    "listing_days"
)

@dataclass(frozen = True)
class DailyEligibilityPolicy:
    """Base inclusion rules shared by every market"""

    min_listing_days: int = 60
    require_tradable: bool = True

    def __post_init__(self) -> None:
        if self.min_listing_days < 0:
            raise ValueError("min_listing_days must be non-negative")

@dataclass(frozen = True)
class DailyEligibilityUniverse:
    """Point-in-time univere built from a daily eligibility status table"""

    _members_by_date: Mapping[pd.Timestamp, frozenset[str]]
    _status_by_key: Mapping[tuple[pd.Timestamp, str], Mapping[str, object]]

    @classmethod
    def from_frame(
        cls,
        frame: pd.DataFrame,
        policy: DailyEligibilityPolicy | None = None,
    ) -> "DailyEligibilityUniverse":
        if not isinstance(frame, pd.DataFrame):
            raise TypeError("eligibility frame must be a pandas DataFrame")

        missing = [column for column in _REQUIRED_COLUMNS if column not in frame.columns]
        if missing:
            raise ValueError(f"missing required columns: {', '.join(missing)}")

        active_policy = policy or DailyEligibilityPolicy()
        normalized = frame.copy()

        normalized["date"] = pd.to_datetime(
            normalized["date"],
            errors = "raise"
        ).dt.normalize()
        normalized["ticker"] = normalized["ticker"].astype(str).str.strip()

        if (normalized["ticker"] == "").any():
            raise ValueError("ticker cannot be empty")

        if normalized.duplicated(["date", "ticker"]).any():
            raise ValueError("eligibility frame contains duplicate date/ticker rows")

        for column in ("is_listed", "is_tradable"):
            if normalized[column].isna().any():
                raise ValueError(f"{column} cannot contain null values")

            normalized[column] = normalized[column].astype(bool)
        normalized["listing_days"] = pd.to_numeric(
            normalized["listing_days"],
            errors = "raise"
        )
        if (normalized["listing_days"] <0).any():
            raise ValueError("listing_days must be non-negative")

        included = (
            normalized["is_listed"] & (normalized["listing_days"] >= active_policy.min_listing_days)
        )

        if active_policy.require_tradable:
            included &= normalized["is_tradable"]

        members_by_date: dict[pd.Timestamp, frozenset[str]] = {}
        for date, group in normalized.loc[included].groupby("date", sort = False):
            members_by_date[date] = frozenset(group["ticker"])

        core_columns = set(_REQUIRED_COLUMNS)
        status_columns = [
            column for column in normalized.columns
            if column not in core_columns
        ]

        status_by_key: dict[tuple[pd.Timestamp, str], Mapping[str, object]] = {}
        for row in normalized.itertuples(index = False):
            values = row._asdict()
            key = (values["date"], values["ticker"])
            status_by_key[key] = MappingProxyType(
                {
                    column: (
                        bool(values[column])
                        if isinstance(values[column], bool)
                        else values[column]
                    )
                    for column in status_columns
                }
            )
        return cls(
            _members_by_date = MappingProxyType(members_by_date),
            _status_by_key = MappingProxyType(status_by_key),
        )

    def get_constituents(self, as_of_date: pd.Timestamp) -> set[str]:
        date = pd.Timestamp(as_of_date).normalize()
        return set(self._members_by_date.get(date, frozenset()))

    def status_on(
            self,
            as_of_date: pd.Timestamp,
            ticker: str,
    ) -> dict[str, object]:
        key = (pd.Timestamp(as_of_date).normalize(),str(ticker))
        return dict(self._status_by_key.get(key, {}))
    

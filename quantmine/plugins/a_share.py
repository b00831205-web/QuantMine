"""Point-in-time A-share eligbility universe primitives"""

from __future__ import annotations

from dataclasses import dataclass, field

from pathlib import Path

from .context import SourceContext
from .contracts import DataBinding, UniverseComponent
from collections.abc import Callable
from .eligibility import DailyEligibilityPolicy, DailyEligibilityUniverse

import pandas as pd
from ..workflows.market_status import DailyMarketStatus

from ..workflows.market_status_storage import ParquetDailyMarketStatusLoader

_REQUIRED_COLUMNS = (
    "date",
    "ticker",
    "is_listed",
    "is_st",
    "is_suspended",
    "listing_days",
    "is_limit_up",
    "is_limit_down",
)

DailyStatusLoader = Callable[[pd.Timestamp], pd.DataFrame]

_SECURITY_STATUS_COLUMNS = (
    "ticker",
    "is_listed",
    "is_st",
    "listing_days"
)

_EXECUTION_STATUS_COLUMNS = (
    "ticker",
    "is_suspended",
    "is_limit_up",
    "is_limit_down",
)

_SECURITY_MASTER_COLUMNS = (
    "listing_id",
    "ticker",
    "list_date",
    "delist_date",
    "exchange",
    "security_type"
)

_A_SHARE_ELIGIBILITY_FRAME_COLUMNS = (
    "date",
    "ticker",
    "is_listed",
    "is_tradable",
    "listing_days",
    "is_st",
    "is_suspended",
    "is_limit_up",
    "is_limit_down"
)

@dataclass(frozen = True)
class AStockSecurityMaster:
    """Point-in-time A-share security master with multiple listring intervals"""

    _records: pd.DataFrame = field(repr=False, compare= False)

    @classmethod
    def from_frame(cls, frame: pd.DataFrame) -> "AStockSecurityMaster":
        if not isinstance(frame, pd.DataFrame):
            raise TypeError("security master must be a pandas DataFrame")

        missing = [
            column for column in _SECURITY_MASTER_COLUMNS if column not in frame.columns
        ]
        if missing:
            raise ValueError(
                "security master is missing required columns: "
                + ", ".join(missing)
            )
        normalized = frame.loc[:, _SECURITY_MASTER_COLUMNS].copy()
        for column in ("listing_id", "ticker", "exchange", "security_type"):
            normalized[column] = normalized[column].astype(str).str.strip()
            if (normalized[column] == "").any():
                raise ValueError(
                    f"security master contains an empty {column!r}"
                )
        normalized["exchange"] = normalized["exchange"].str.upper()
        normalized["security_type"] = normalized["security_type"].str.upper()

        if normalized["listing_id"].duplicated().any():
            raise ValueError("security master contains duplicate listing_id")

        normalized["list_date"] = pd.to_datetime(
            normalized["list_date"],
            errors = "raise",
        ).dt.normalize()
        normalized["delist_date"] = pd.to_datetime(
            normalized["delist_date"],
            errors= "coerce"
        ).dt.normalize()

        invalid_range = (
            normalized["delist_date"].notna() & (normalized["delist_date"] < normalized["list_date"])
        )
        if invalid_range.any():
            raise ValueError(
                "security master contains delist_date before list_date"
            )

        normalized = normalized.sort_values(
            ["ticker", "list_date", "listing_id"]
        ).reset_index(drop=True)

        for ticker, intervals in normalized.groupby("ticker", sort=False):
            previous_end: pd.Timestamp | None = None

            for row in intervals.itertuples(index = False):
                if (previous_end is not None and row.list_date < previous_end):
                    raise ValueError(
                        "security master contains overlapping listing intervals"
                        f"for ticker {ticker!r}"
                    )
                previous_end = (
                    pd.Timestamp.max if pd.isna(row.delist_date) else row.delist_date
                )

        return cls(_records = normalized)

    def to_frame(self) -> pd.DataFrame:
        """Return a defensive copy of the normalized security-master records"""

        return self._records.copy(deep = True)
                    

    def status_on(
            self,
            as_of_date: pd.Timestamp,
            *,
            trading_calendar: pd.DatetimeIndex,
    ) -> pd.DataFrame:
        date = pd.Timestamp(as_of_date).normalize()
        calendar = pd.DatetimeIndex(
            pd.to_datetime(trading_calendar, errors = "raise")
        ).normalize()

        if calendar.has_duplicates:
            raise ValueError("trading_calendar contains duplicate dates")

        if date not in calendar:
            raise ValueError(
                f"as_of_date {date.date().isoformat()} is not in trading_calendar"
            )

        calendar = calendar.sort_values()
        rows: list[dict[str, object]] = []

        for ticker, intervals in self._records.groupby("ticker", sort=True):
            active = intervals.loc[(
                intervals["list_date"] <= date
            ) & (
                intervals["delist_date"].isna() | (date < intervals["delist_date"])
            )]
            if not active.empty:
                selected = active.iloc[0]
                is_listed = True
                listing_days = int(
                    (
                        (calendar >= selected["list_date"]) & (calendar <= date)
                    ).sum()
                )
            else:
                past = intervals.loc[intervals["list_date"] <= date]
                selected = (
                    past.iloc[-1]
                    if not past.empty
                    else intervals.iloc[0]
                )
                is_listed = False
                listing_days = 0
            rows.append(
                {
                    "listing_id":selected["listing_id"],
                    "ticker": ticker,
                    "is_listed": is_listed,
                    "listing_days": listing_days,
                    "exchange": selected["exchange"],
                    "security_type": selected["security_type"]
                }
            )
        return pd.DataFrame(rows)

MarketStatusLoader = Callable[[pd.Timestamp], DailyMarketStatus]

@dataclass(frozen = True)
class AStockDailyMarketStatusEligibilityBuilder:
    """Adapt generic daily market status into A-share eligibility input"""

    status_loader: MarketStatusLoader = field(
        repr = False,
        compare = False,
    )
    policy: "AStockEligibilityPolicy" = field(
        default_factory = lambda: AStockEligibilityPolicy()
    )
    def build(self, as_of_date: pd.Timestamp) -> pd.DataFrame:
        date = pd.Timestamp(as_of_date).normalize()
        status = self.status_loader(date)

        if not isinstance(status, DailyMarketStatus):
            raise TypeError(
                "status loader must return a DailyMarketStatus"
            )
        if status.as_of_date != date:
            raise ValueError(
                "daily market status date does not match requested date"
            )

        frame = status.frame
        missing = [
            column for column in _A_SHARE_ELIGIBILITY_FRAME_COLUMNS
            if column not in frame.columns
        ]
        if missing:
            raise ValueError(
                "A-share daily market status is missing required columns: "
                + ", ".join(missing)
            )

        eligibility = frame.loc[
            :,
            _A_SHARE_ELIGIBILITY_FRAME_COLUMNS,
        ].copy()

        eligibility["is_tradable"] &= eligibility["is_listed"]

        if self.policy.exclude_st:
            eligibility["is_tradable"] &= ~eligibility["is_st"]

        if self.policy.exclude_suspended:
            eligibility["is_tradable"] &= ~eligibility["is_suspended"]

        

        return (
            eligibility.sort_values("ticker").reset_index(drop=True)
        )

@dataclass(frozen = True)
class AStockEligibilityPolicy:
    """Signal-date membership rules; execution constraints stay as status data"""

    min_listing_days: int = 60
    exclude_st: bool = True
    exclude_suspended: bool = True

    def __post_init__(self) -> None:
        if self.min_listing_days < 0:
            raise ValueError("min_listing_days must be non-negative")

@dataclass(frozen = True)
class AStockEligibilityUniverse:
    """Audited daily A-share membership with preserved execution status"""

    _universe: DailyEligibilityUniverse

    @classmethod
    def from_frame(
        cls,
        frame: pd.DataFrame,
        *,
        policy: AStockEligibilityPolicy | None = None,
    ) -> "AStockEligibilityUniverse":
        if not isinstance(frame, pd.DataFrame):
            raise TypeError("A-share eligibility data must be a DataFrame")

        missing = [
            column for column in _REQUIRED_COLUMNS if column not in frame.columns
        ]

        if missing:
            raise ValueError(
                "A-share eligibility data is missing required columns: "
                +", ".join(missing)
            )

        active_policy = policy or AStockEligibilityPolicy()
        normalized = frame.loc[:, _REQUIRED_COLUMNS].copy()

        for column in (
            "is_st",
            "is_suspended",
            "is_limit_up",
            "is_limit_down",
        ):
            if normalized[column].isna().any():
                raise ValueError(
                    f"A-share eligibility data contains null {column!r}"
                )
            normalized[column] = normalized[column].astype(bool)

        normalized["is_tradable"] = True
        if active_policy.exclude_st:
            normalized["is_tradable"] &= ~normalized["is_st"]
        if active_policy.exclude_suspended:
            normalized["is_tradable"] &= ~normalized["is_suspended"]

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
            ticker: str
    ) -> dict[str, bool]:
        status = self._universe.status_on(date, ticker)
        if not status:
            normalized_date = pd.Timestamp(date).normalize()
            raise KeyError(
                f"No A-share eligibility status for {ticker!r} "
                f"on {normalized_date.date().isoformat()}"
            )

        return {
            "is_limit_up": bool(status["is_limit_up"]),
            "is_limit_down": bool(status["is_limit_down"]),
        }

@dataclass(frozen = True)
class ParquetAStockEligibilityUniversePlugin:
    """Load audited daily eligibility rows from a named Parquet lake."""

    eligibility_file: str = "eligibility.parquet"
    policy: AStockEligibilityPolicy = field(
        default_factory=AStockEligibilityPolicy
    )

    def __post_init__(self) -> None:
        if Path(self.eligibility_file).is_absolute():
            raise ValueError("eligibility_file must be a relative path")

    def load(
            self,
            binding: DataBinding,
            context: SourceContext
    ) -> AStockEligibilityUniverse:
        if binding.eligibility_binding is not None:
            eligibility = binding.eligibility_binding
            if eligibility.market != "CN": 
                raise ValueError(
                    "A-share eligibility plugin requires "
                    "eligibility_binding.market='CN'"
                )

            lake_root = context.connections.parquet_root(
                eligibility.connection_ref
            ).resolve()
            dataset_root = (lake_root / eligibility.dataset).resolve()

            try:
                dataset_root.relative_to(lake_root)

            except ValueError as error:
                raise ValueError(
                    f"Eligibility dataset path {eligibility.dataset!r} "
                    f"escapes the configured lake root"
                ) from error
            version_root = (
                dataset_root / "versions" / eligibility.version
            ).resolve()
            try: 
                version_root.relative_to(dataset_root)
            except ValueError as error:
                raise ValueError(
                    f"Eligibility version {eligibility.version!r} "
                    "escapes the configured dataset root"
                ) from error
            path = (version_root / self.eligibility_file).resolve()
            try:
                path.relative_to(version_root)

            except ValueError as error:
                raise ValueError(
                    f"Eligibility version {self.eligibility_file!r} "
                    "escapes the configured version root"
                ) from error
        else:
            if binding.connection_ref is None:
                raise ValueError(
                    "ParquetAStockEligibilityUniversePlugin requires "
                    "DataBinding.connection_ref"
                )
            if not binding.universe_dataset:
                raise ValueError(
                    "ParquetAStockEligibilityUniversePlugin requires "
                    "DataBinding.universe_dataset"
                )
            lake_root = context.connections.parquet_root(
                binding.connection_ref
            ).resolve()
            dataset_root = (lake_root / binding.universe_dataset).resolve()

            try:
                dataset_root.relative_to(lake_root)
            except ValueError as error:
                raise ValueError(
                    f"Universe dataset path {binding.universe_dataset!r} "
                    "escapes the configured lake root"
                ) from error

            path = (dataset_root / self.eligibility_file).resolve()
            try:
                path.relative_to(dataset_root)
            except ValueError as error:
                raise ValueError(
                    f"Eligibility file {self.eligibility_file!r} "
                    f"escapes universe dataset {binding.universe_dataset!r}"
                ) from error

        if not path.is_file():
            raise FileNotFoundError(
                f"Eligibility Parquet file does not exist: {path}"
            )

        return AStockEligibilityUniverse.from_frame(
                pd.read_parquet(path),
                policy=self.policy
        )

def create_cn_a_share_eligibility_universe(
        **params: object,
) -> UniverseComponent:
    return UniverseComponent(
        id = "cn_a_share_daily_eligibility",
        plugin = ParquetAStockEligibilityUniversePlugin(**params),
        requires_connection = True,
        metadata = {
            "market": "CN",
            "storage": "parquet",
            "schema": "daily_eligibility_v1"
        }
    )

def create_parquet_a_share_market_status_eligibility_builder(
        context: SourceContext,
        *,
        connection_ref: str,
        dataset: str,
        version: str,
        market: str = "CN",
        policy: "AStockEligibilityPolicy | None" = None 
) -> AStockDailyMarketStatusEligibilityBuilder:
    """Build A-share eligibility input from persisted generic market status."""
    status_loader = ParquetDailyMarketStatusLoader(
        context = context,
        connection_ref = connection_ref,
        dataset = dataset,
        market = market,
        version = version,
    )
    return AStockDailyMarketStatusEligibilityBuilder(
        status_loader = status_loader.load,
        policy = policy or AStockEligibilityPolicy()
    )
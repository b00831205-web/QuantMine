"""Loading versioned A-share security-master and trading-calendar data"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from ..plugins.a_share import AStockSecurityMaster
from ..plugins.context import SourceContext

@dataclass(frozen = True)
class AStockReferenceData:
    security_master: AStockSecurityMaster
    trading_calendar: pd.DatetimeIndex

@dataclass(frozen = True)
class ParquetAStockReferenceLoader:
    """Load one immutable A-share reference-data version from a Parquet lake."""

    context: SourceContext = field(repr = False, compare = False)
    connection_ref: str
    dataset: str
    version: str

    def __post_init__(self) -> None:
        for label, value in (
            ("dataset", self.dataset),
            ("version", self.version)
        ):
            if not value or value.strip()!=value:
                raise ValueError(f"{label} must be a non-empty trimmed string")
            if "/" in value or "\\" in value or value in {".", ".."}:
                raise ValueError(f"{label} must be a safe path segment")

        self._version_root()

    def load(self) -> AStockReferenceData:
        version_root = self._version_root()
        master_path = version_root / "security_master.parquet"
        calendar_path = version_root / "trading_calendar.parquet"

        for path, label in (
            (master_path, "security master"),
            (calendar_path, "trading calendar")
        ):
            if not path.is_file():
                raise FileNotFoundError(f"{label} Parquet file does not exist: {path}")

        security_master = AStockSecurityMaster.from_frame(
            pd.read_parquet(master_path)
        )

        calendar_frame = pd.read_parquet(calendar_path)
        if not isinstance(calendar_frame, pd.DataFrame):
            raise TypeError("trading calendar Parquet did not produce a DataFrame")

        if "date" not in calendar_frame.columns:
            raise ValueError("trading calendar is missing required column: date")

        trading_calendar = pd.DatetimeIndex(
            pd.to_datetime(calendar_frame["date"], errors = "raise")
        ).normalize()

        if trading_calendar.has_duplicates:
            raise ValueError("trading calendar contains duplicate dates")

        return AStockReferenceData(
            security_master = security_master,
            trading_calendar= trading_calendar.sort_values(),
        )

    def _version_root(self) -> Path:
        lake_root = self.context.connections.parquet_root(
            self.connection_ref
        ).resolve()
        dataset_root = (lake_root / self.dataset).resolve()

        try:
            dataset_root.relative_to(lake_root)

        except ValueError as error:
            raise ValueError(
                f"dataset path {self.dataset!r} escapes the configured lake root"
            ) from error

        version_root = (dataset_root / "versions" / self.version).resolve()
        try:
            version_root.relative_to(dataset_root)
        except ValueError as error:
            raise ValueError(f"reference version {self.version!r} escapes the dataset root") from error

        return version_root

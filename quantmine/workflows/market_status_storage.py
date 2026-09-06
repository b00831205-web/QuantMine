"""Parquet storage adapter for immutable daily market-status partitions"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path

import pandas as pd

from ..plugins.context import SourceContext

from .market_status import DailyMarketStatus

@dataclass(frozen = True)
class ParquetDailyMarketStatusLoader:
    """Load one versioned market-status partition from a Parquet lake"""

    context: SourceContext = field(repr = False, compare = False)
    connection_ref: str
    dataset: str
    market: str
    version: str

    def __post_init__(self) -> None:
        for label, value in (
            ("dataset", self.dataset),
            ("market", self.market),
            ("version", self.version)
        ):
            if not value or value.strip() != value:
                raise ValueError(f"{label} must be a non-empty trimmed string")

            if "/" in value or "\\" in value or value in {".", ".."}:
                raise ValueError(f"{label} must be a safe path segment")

        self._dataset_root()

    def load(
            self,
            as_of_date: pd.Timestamp | str,
    ) -> DailyMarketStatus:
        date = pd.Timestamp(as_of_date).normalize()
        output_dir = self._output_dir(date)
        status_path = output_dir / "status.parquet"
        manifest_path = output_dir / "manifest.json"

        if not status_path.is_file():
            raise FileNotFoundError(
                f"market-status Parquet file does not exist: {status_path}"
            )

        if not manifest_path.is_file():
            raise FileNotFoundError(
                f"market-status manifest does not exist: {manifest_path}"
            )

        manifest = json.loads(manifest_path.read_text(encoding = "utf-8"))
        expected = {
            "dataset_id": self.dataset,
            "market": self.market,
            "version": self.version,
            "as_of_date": date.date().isoformat(),
        }

        if any(manifest.get(key)!=value for key, value in expected.items()):
            raise ValueError(
                "market-status manifest does not match requested partition"
            )

        frame = pd.read_parquet(status_path)
        if not isinstance(frame, pd.DataFrame):
            raise TypeError(
                "market-status Parquet file did not produce a DataFrame"
            )

        status = DailyMarketStatus.from_frame(frame)
        if status.as_of_date != date:
            raise ValueError(
                "market-status data does not match requested partition"
            )

        return status

    def _dataset_root(self) -> Path:
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

        return dataset_root

    def _output_dir(self, date: pd.Timestamp) -> Path:
        dataset_root = self._dataset_root()
        output_dir = (
            dataset_root / f"market={self.market}" / f"date={date.date().isoformat()}" / "versions" / self.version
        ).resolve()

        try:
            output_dir.relative_to(dataset_root)

        except ValueError as error:
            raise ValueError(
                "market_status partition escapes the configured dataset root"
            ) from error

        return output_dir
"""Tests for reading one generic daily market-status partition from Parquet."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from quantmine.plugins.context import SourceContext
from quantmine.storage.connections import (
    ConnectionKind,
    ConnectionRegistry,
    DataConnectionConfig,
)
from quantmine.workflows.market_status import DailyMarketStatus
from quantmine.workflows.market_status_publication import (
    MarketStatusPublishSpec,
    publish_daily_market_status,
)
from quantmine.workflows.market_status_storage import (
    ParquetDailyMarketStatusLoader,
)


def _context(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> SourceContext:
    lake_root = tmp_path / "lake"
    lake_root.mkdir()
    monkeypatch.setenv("QUANTMINE_STATUS_LAKE_ROOT", str(lake_root))

    return SourceContext(
        connections=ConnectionRegistry(
            {
                "status_lake": DataConnectionConfig(
                    kind=ConnectionKind.PARQUET,
                    root_env="QUANTMINE_STATUS_LAKE_ROOT",
                )
            }
        ),
        run_id=1401,
        artifact_dir=tmp_path / "artifacts",
    )


def _published_status(root: Path) -> None:
    status = DailyMarketStatus.from_frame(
        pd.DataFrame(
            {
                "date": ["2024-01-02", "2024-01-02"],
                "ticker": ["000001", "000002"],
                "is_listed": [True, True],
                "is_tradable": [True, False],
                "listing_days": [100, 100],
                "is_st": [False, True],
                "is_suspended": [False, True],
            }
        )
    )
    publish_daily_market_status(
        status,
        root=root,
        spec=MarketStatusPublishSpec(
            dataset_id="daily_market_status",
            market="CN",
            version="history_v1",
            source="fixture",
        ),
    )


def test_loader_reads_one_market_date_and_version(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)
    _published_status(context.connections.parquet_root("status_lake"))

    status = ParquetDailyMarketStatusLoader(
        context=context,
        connection_ref="status_lake",
        dataset="daily_market_status",
        market="CN",
        version="history_v1",
    ).load("2024-01-02 14:30:00")

    assert status.as_of_date == pd.Timestamp("2024-01-02")
    assert status.frame.to_dict("records") == [
        {
            "date": pd.Timestamp("2024-01-02"),
            "ticker": "000001",
            "is_listed": True,
            "is_tradable": True,
            "listing_days": 100,
            "is_st": False,
            "is_suspended": False,
        },
        {
            "date": pd.Timestamp("2024-01-02"),
            "ticker": "000002",
            "is_listed": True,
            "is_tradable": False,
            "listing_days": 100,
            "is_st": True,
            "is_suspended": True,
        },
    ]


def test_loader_rejects_a_dataset_path_escape(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="safe path segment"):
        ParquetDailyMarketStatusLoader(
            context=context,
            connection_ref="status_lake",
            dataset="../escape",
            market="CN",
            version="history_v1",
        )

"""Tests for wiring persisted generic status into the A-share adapter."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from quantmine.plugins.a_share import (
    create_parquet_a_share_market_status_eligibility_builder,
)
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


def _context(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> SourceContext:
    lake_root = tmp_path / "lake"
    lake_root.mkdir()
    monkeypatch.setenv("QUANTMINE_A_SHARE_STATUS_LAKE", str(lake_root))

    return SourceContext(
        connections=ConnectionRegistry(
            {
                "a_share_status_lake": DataConnectionConfig(
                    kind=ConnectionKind.PARQUET,
                    root_env="QUANTMINE_A_SHARE_STATUS_LAKE",
                )
            }
        ),
        run_id=1501,
        artifact_dir=tmp_path / "artifacts",
    )


def _publish_a_share_status(root: Path) -> None:
    publish_daily_market_status(
        DailyMarketStatus.from_frame(
            pd.DataFrame(
                {
                    "date": ["2024-01-02", "2024-01-02"],
                    "ticker": ["000001", "000002"],
                    "is_listed": [True, True],
                    "is_tradable": [True, True],
                    "listing_days": [100, 100],
                    "is_st": [False, True],
                    "is_suspended": [False, False],
                    "is_limit_up": [False, True],
                    "is_limit_down": [False, False],
                }
            )
        ),
        root=root,
        spec=MarketStatusPublishSpec(
            dataset_id="daily_market_status",
            market="CN",
            version="history_v1",
            source="fixture",
        ),
    )


def test_factory_builds_a_share_eligibility_input_from_generic_status(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)
    _publish_a_share_status(
        context.connections.parquet_root("a_share_status_lake")
    )

    builder = create_parquet_a_share_market_status_eligibility_builder(
        context,
        connection_ref="a_share_status_lake",
        dataset="daily_market_status",
        version="history_v1",
    )

    frame = builder.build(pd.Timestamp("2024-01-02"))

    assert frame["ticker"].tolist() == ["000001", "000002"]
    assert frame["is_tradable"].tolist() == [True, False]
    assert frame["is_st"].tolist() == [False, True]
    assert frame["is_limit_up"].tolist() == [False, True]

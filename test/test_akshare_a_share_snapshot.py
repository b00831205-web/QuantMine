"""Tests for forward-only raw AkShare A-share status snapshot collection."""

from __future__ import annotations

from datetime import datetime, timezone
import json

import pandas as pd
import pytest

from quantmine.workflows.akshare_a_share_snapshot import (
    AkShareAStockRawSnapshotCollector,
    LiveSnapshotDateMismatchError,
)


def _spot_snapshot() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "代码": ["000001", "000002"],
            "名称": ["平安银行", "ST示例"],
            "最新价": [10.0, 5.0],
            "成交量": [100_000, 20_000],
        }
    )


def _suspension_snapshot(date: str) -> pd.DataFrame:
    assert date == "20240102"
    return pd.DataFrame(
        {
            "代码": ["000002"],
            "名称": ["ST示例"],
            "停牌时间": ["2024-01-02"],
        }
    )


def test_collector_persists_one_raw_daily_snapshot_with_manifest(tmp_path) -> None:
    collector = AkShareAStockRawSnapshotCollector(
        spot_loader=_spot_snapshot,
        suspension_loader=_suspension_snapshot,
        clock=lambda: datetime(2024, 1, 2, 8, tzinfo=timezone.utc),
    )

    snapshot = collector.collect(
        as_of_date="2024-01-02 15:30:00",
        root=tmp_path,
    )

    expected_dir = tmp_path / "akshare_a_share_raw" / "2024-01-02"
    assert snapshot.output_dir == expected_dir
    assert pd.read_parquet(snapshot.spot_path)["代码"].tolist() == [
        "000001",
        "000002",
    ]
    assert pd.read_parquet(snapshot.suspension_path)["代码"].tolist() == [
        "000002",
    ]

    manifest = json.loads(snapshot.manifest_path.read_text(encoding="utf-8"))
    assert manifest == {
        "as_of_date": "2024-01-02",
        "provider": "akshare",
        "spot_row_count": 2,
        "suspension_row_count": 1,
    }


def test_collector_allows_an_empty_daily_suspension_snapshot(tmp_path) -> None:
    collector = AkShareAStockRawSnapshotCollector(
        spot_loader=_spot_snapshot,
        suspension_loader=lambda _: pd.DataFrame(
            columns=["代码", "名称", "停牌时间"]
        ),
        clock=lambda: datetime(2024, 1, 2, 8, tzinfo=timezone.utc),
    )

    snapshot = collector.collect(as_of_date="2024-01-02", root=tmp_path)

    assert snapshot.suspension_row_count == 0
    assert snapshot.suspension_path.is_file()


def test_collector_rejects_historical_label_before_loading_or_writing(
    tmp_path,
) -> None:
    calls: list[str] = []
    collector = AkShareAStockRawSnapshotCollector(
        spot_loader=lambda: calls.append("spot") or _spot_snapshot(),
        suspension_loader=lambda date: (
            calls.append(f"suspension:{date}")
            or _suspension_snapshot(date)
        ),
        clock=lambda: datetime(2024, 1, 3, 1, tzinfo=timezone.utc),
    )

    with pytest.raises(
        LiveSnapshotDateMismatchError,
        match=(
            "refusing to label live AkShare data as 2024-01-02.*"
            "current Asia/Shanghai market date is 2024-01-03"
        ),
    ):
        collector.collect(
            as_of_date="2024-01-02",
            root=tmp_path,
        )

    assert calls == []
    assert list(tmp_path.iterdir()) == []


def test_collector_rejects_a_naive_clock_before_loading(
    tmp_path,
) -> None:
    collector = AkShareAStockRawSnapshotCollector(
        spot_loader=_spot_snapshot,
        suspension_loader=_suspension_snapshot,
        clock=lambda: datetime(2024, 1, 2, 8),
    )

    with pytest.raises(ValueError, match="timezone-aware datetime"):
        collector.collect(
            as_of_date="2024-01-02",
            root=tmp_path,
        )

    assert list(tmp_path.iterdir()) == []

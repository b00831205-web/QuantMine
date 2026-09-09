"""Tests for forward-only raw AkShare A-share status snapshot collection."""

from __future__ import annotations

from datetime import datetime, time, timezone
import json
import sys
from types import ModuleType

import pandas as pd
import pytest

from quantmine.workflows import akshare_a_share_snapshot as snapshot_module
from quantmine.workflows.akshare_a_share_snapshot import (
    AkShareAStockRawSnapshotCollector,
    LiveSnapshotDateMismatchError,
)


def _spot_snapshot(date: str | None = None) -> pd.DataFrame:
    if date is not None:
        assert date == "20240102"
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
        "schema_version": "a_share_raw_snapshot_v3",
        "spot_source": "custom",
        "spot_row_count": 2,
        "suspension_source": "custom",
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
        spot_loader=lambda date: (
            calls.append(f"spot:{date}") or _spot_snapshot(date)
        ),
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


def test_collector_rejects_a_current_date_before_snapshot_is_available(
    tmp_path,
) -> None:
    calls: list[str] = []
    collector = AkShareAStockRawSnapshotCollector(
        spot_loader=lambda date: calls.append(f"spot:{date}") or _spot_snapshot(date),
        suspension_loader=lambda date: (
            calls.append(f"suspension:{date}") or _suspension_snapshot(date)
        ),
        clock=lambda: datetime(2024, 1, 2, 7, 14, tzinfo=timezone.utc),
    )

    with pytest.raises(
        snapshot_module.LiveSnapshotNotReadyError,
        match=(
            "live A-share snapshot for 2024-01-02 "
            "is not available before 15:15:00 Asia/Shanghai"
        ),
    ):
        collector.collect(as_of_date="2024-01-02", root=tmp_path)

    assert calls == []
    assert list(tmp_path.iterdir()) == []


def test_collector_allows_collection_at_configured_availability_time(
    tmp_path,
) -> None:
    collector = AkShareAStockRawSnapshotCollector(
        spot_loader=_spot_snapshot,
        suspension_loader=_suspension_snapshot,
        clock=lambda: datetime(2024, 1, 2, 7, 5, tzinfo=timezone.utc),
        snapshot_available_after=time(15, 5),
    )

    snapshot = collector.collect(as_of_date="2024-01-02", root=tmp_path)

    assert snapshot.spot_row_count == 2
    assert snapshot.output_dir.is_dir()


def test_default_network_loaders_use_shared_http_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, object]] = []
    labels: list[str] = []
    spot = _spot_snapshot()
    suspension = _suspension_snapshot("20240102")

    akshare = ModuleType("akshare")

    def load_spot() -> pd.DataFrame:
        calls.append(("spot", None))
        return spot

    def load_fallback_spot() -> pd.DataFrame:
        calls.append(("fallback_spot", None))
        return spot

    def load_suspension(*, date: str) -> pd.DataFrame:
        calls.append(("suspension", date))
        return suspension

    akshare.stock_zh_a_spot_em = load_spot
    akshare.stock_zh_a_spot = load_fallback_spot
    akshare.stock_tfp_em = load_suspension
    monkeypatch.setitem(sys.modules, "akshare", akshare)

    def fake_retry(operation, *, label: str):
        labels.append(label)
        return operation()

    monkeypatch.setattr(
        snapshot_module,
        "retry_http_call",
        fake_retry,
    )

    loaded_spot = snapshot_module._default_spot_loader("20240102")
    loaded_suspension = snapshot_module._default_suspension_loader("20240102")

    assert loaded_spot is spot
    assert loaded_spot.attrs["upstream_source"] == "eastmoney"
    assert loaded_suspension is suspension
    assert loaded_suspension.attrs["upstream_source"] == "eastmoney"
    assert calls == [
        ("spot", None),
        ("suspension", "20240102"),
    ]
    assert labels == [
        "AkShare Eastmoney A-share spot snapshot",
        "AkShare A-share suspension snapshot",
    ]


def test_default_spot_loader_falls_back_to_sina_after_transient_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    labels: list[str] = []
    fallback_spot = _spot_snapshot()
    fallback_spot["代码"] = ["sz000001", "sh000002"]
    limit_up = pd.DataFrame({"代码": ["000001"]})
    limit_down = pd.DataFrame({"代码": ["000002"]})

    akshare = ModuleType("akshare")
    akshare.stock_zh_a_spot_em = lambda: calls.append("eastmoney")
    akshare.stock_zh_a_spot = lambda: (
        calls.append("sina") or fallback_spot
    )
    akshare.stock_zt_pool_em = lambda *, date: (
        calls.append(f"limit_up:{date}") or limit_up
    )
    akshare.stock_zt_pool_dtgc_em = lambda *, date: (
        calls.append(f"limit_down:{date}") or limit_down
    )
    monkeypatch.setitem(sys.modules, "akshare", akshare)

    class TemporaryNetworkError(Exception):
        pass

    def fake_retry(operation, *, label: str):
        labels.append(label)
        if "Eastmoney" in label:
            calls.append("eastmoney")
            raise TemporaryNetworkError("temporary failure")
        return operation()

    monkeypatch.setattr(snapshot_module, "retry_http_call", fake_retry)
    monkeypatch.setattr(
        snapshot_module,
        "is_transient_http_error",
        lambda error: isinstance(error, TemporaryNetworkError),
    )

    result = snapshot_module._default_spot_loader("20240102")

    assert result is not fallback_spot
    assert result["代码"].tolist() == ["000001", "000002"]
    assert result["is_limit_up"].tolist() == [True, False]
    assert result["is_limit_down"].tolist() == [False, True]
    assert result.attrs["upstream_source"] == "sina+eastmoney_limit_pools"
    assert calls == [
        "eastmoney",
        "sina",
        "limit_up:20240102",
        "limit_down:20240102",
    ]
    assert labels == [
        "AkShare Eastmoney A-share spot snapshot",
        "AkShare Sina A-share spot snapshot",
        "AkShare A-share limit-up pool",
        "AkShare A-share limit-down pool",
    ]


def test_default_spot_loader_does_not_hide_non_transient_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    akshare = ModuleType("akshare")
    akshare.stock_zh_a_spot_em = lambda: None
    akshare.stock_zh_a_spot = lambda: calls.append("sina")
    monkeypatch.setitem(sys.modules, "akshare", akshare)

    def fake_retry(operation, *, label: str):
        raise ValueError("invalid response schema")

    monkeypatch.setattr(snapshot_module, "retry_http_call", fake_retry)
    monkeypatch.setattr(
        snapshot_module,
        "is_transient_http_error",
        lambda error: False,
    )

    with pytest.raises(ValueError, match="invalid response schema"):
        snapshot_module._default_spot_loader("20240102")

    assert calls == []

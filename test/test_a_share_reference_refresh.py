"""Tests for the AkShare A-share reference refresh workflow."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from quantmine.plugins.a_share import AStockSecurityMaster
from quantmine.plugins.context import SourceContext
from quantmine.plugins.contracts import VersionedDatasetBinding
from quantmine.storage.connections import (
    ConnectionKind,
    ConnectionRegistry,
    DataConnectionConfig,
)
from quantmine.workflows.a_share_reference import AStockReferenceData
from quantmine.workflows.a_share_reference_refresh import (
    refresh_akshare_a_stock_reference,
)


class _Collector:
    def __init__(self, reference: AStockReferenceData) -> None:
        self.reference = reference
        self.calls = 0

    def collect(self) -> AStockReferenceData:
        self.calls += 1
        return self.reference


class _FailingCollector:
    def collect(self) -> AStockReferenceData:
        raise RuntimeError("upstream collection failed")


def _reference() -> AStockReferenceData:
    master = AStockSecurityMaster.from_frame(
        pd.DataFrame(
            {
                "listing_id": ["SZSE:000001:19910403"],
                "ticker": ["000001"],
                "list_date": ["1991-04-03"],
                "delist_date": [None],
                "exchange": ["SZSE"],
                "security_type": ["COMMON_STOCK"],
            }
        )
    )
    return AStockReferenceData(
        security_master=master,
        trading_calendar=pd.DatetimeIndex(
            ["2026-09-04", "2026-09-07"]
        ),
    )


def _binding(market: str = "CN") -> VersionedDatasetBinding:
    return VersionedDatasetBinding(
        connection_ref="cn_reference",
        dataset="cn_a_share_reference",
        market=market,
        version="20260906",
    )


def _context(
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
) -> SourceContext:
    monkeypatch.setenv("REFERENCE_ROOT", str(root))
    return SourceContext(
        connections=ConnectionRegistry(
            {
                "cn_reference": DataConnectionConfig(
                    kind=ConnectionKind.PARQUET,
                    root_env="REFERENCE_ROOT",
                    read_only=False,
                )
            }
        ),
        run_id=0,
        artifact_dir=root / "artifacts",
    )


def test_refresh_collects_then_publishes_configured_version(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "lake"
    root.mkdir()
    collector = _Collector(_reference())

    publication = refresh_akshare_a_stock_reference(
        _context(monkeypatch, root),
        binding=_binding(),
        collector=collector,
    )

    assert collector.calls == 1
    assert publication.output_dir == (
        root
        / "cn_a_share_reference"
        / "versions"
        / "20260906"
    )
    assert publication.security_master_path.is_file()
    assert publication.trading_calendar_path.is_file()
    assert publication.manifest_path.is_file()


def test_refresh_does_not_touch_destination_when_collection_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "lake"
    root.mkdir()

    with pytest.raises(RuntimeError, match="upstream collection failed"):
        refresh_akshare_a_stock_reference(
            _context(monkeypatch, root),
            binding=_binding(),
            collector=_FailingCollector(),
        )

    assert list(root.iterdir()) == []


def test_refresh_rejects_non_cn_binding_before_collection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "lake"
    root.mkdir()
    collector = _Collector(_reference())

    with pytest.raises(ValueError, match="market must be 'CN'"):
        refresh_akshare_a_stock_reference(
            _context(monkeypatch, root),
            binding=_binding(market="US"),
            collector=collector,
        )

    assert collector.calls == 0
    assert list(root.iterdir()) == []

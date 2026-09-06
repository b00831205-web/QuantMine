"""Tests for loading versioned A-share reference data from a Parquet lake."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from quantmine.plugins.context import SourceContext
from quantmine.workflows.a_share_reference import ParquetAStockReferenceLoader
from quantmine.storage.connections import (
    ConnectionKind,
    ConnectionRegistry,
    DataConnectionConfig,
)


def _context(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> SourceContext:
    lake_root = tmp_path / "lake"
    lake_root.mkdir()
    monkeypatch.setenv("QUANTMINE_CN_REFERENCE_ROOT", str(lake_root))

    return SourceContext(
        connections=ConnectionRegistry(
            {
                "cn_reference_lake": DataConnectionConfig(
                    kind=ConnectionKind.PARQUET,
                    root_env="QUANTMINE_CN_REFERENCE_ROOT",
                )
            }
        ),
        run_id=1301,
        artifact_dir=tmp_path / "artifacts",
    )


def _write_reference_data(root: Path) -> None:
    version_root = root / "cn_a_share_reference" / "versions" / "2026-08-29"
    version_root.mkdir(parents=True)

    pd.DataFrame(
        {
            "listing_id": ["000001-1"],
            "ticker": ["000001"],
            "list_date": ["2020-01-01"],
            "delist_date": [None],
            "exchange": ["SZSE"],
            "security_type": ["COMMON_STOCK"],
        }
    ).to_parquet(version_root / "security_master.parquet")
    pd.DataFrame({"date": ["2024-01-02", "2024-01-03"]}).to_parquet(
        version_root / "trading_calendar.parquet"
    )


def test_loader_reads_a_versioned_master_and_trading_calendar(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)
    _write_reference_data(context.connections.parquet_root("cn_reference_lake"))

    reference = ParquetAStockReferenceLoader(
        context=context,
        connection_ref="cn_reference_lake",
        dataset="cn_a_share_reference",
        version="2026-08-29",
    ).load()

    assert reference.trading_calendar.tolist() == [
        pd.Timestamp("2024-01-02"),
        pd.Timestamp("2024-01-03"),
    ]
    assert reference.security_master.status_on(
        pd.Timestamp("2024-01-03"),
        trading_calendar=reference.trading_calendar,
    )["listing_days"].tolist() == [2]


def test_loader_rejects_a_reference_dataset_path_escape(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="safe path segment"):
        ParquetAStockReferenceLoader(
            context=context,
            connection_ref="cn_reference_lake",
            dataset="../escape",
            version="2026-08-29",
        )

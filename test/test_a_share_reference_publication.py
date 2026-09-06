"""Immutable publication of A-share security-master and calendar data."""

from pathlib import Path

import pandas as pd
import pytest

from quantmine.plugins.a_share import AStockSecurityMaster
from quantmine.plugins.context import SourceContext
from quantmine.storage.connections import (
    ConnectionKind,
    ConnectionRegistry,
    DataConnectionConfig,
)
from quantmine.workflows.a_share_reference import (
    ParquetAStockReferenceLoader,
)
from quantmine.workflows.a_share_reference_publication import (
    AStockReferencePublishSpec,
    publish_a_stock_reference,
)


def _master(ticker: str = "000001") -> AStockSecurityMaster:
    return AStockSecurityMaster.from_frame(
        pd.DataFrame(
            {
                "listing_id": [f"{ticker}-1"],
                "ticker": [ticker],
                "list_date": ["1991-04-03"],
                "delist_date": [None],
                "exchange": ["SZSE"],
                "security_type": ["COMMON_STOCK"],
            }
        )
    )


def _spec() -> AStockReferencePublishSpec:
    return AStockReferencePublishSpec(
        dataset_id="cn_a_share_reference",
        market="CN",
        version="20260830",
        source="akshare",
    )


def _context(monkeypatch, root: Path) -> SourceContext:
    monkeypatch.setenv("REFERENCE_ROOT", str(root))
    return SourceContext(
        connections=ConnectionRegistry(
            {
                "cn_reference": DataConnectionConfig(
                    kind=ConnectionKind.PARQUET,
                    root_env="REFERENCE_ROOT",
                )
            }
        ),
        run_id=0,
        artifact_dir=root / "artifacts",
    )


def test_publication_round_trips_through_the_existing_loader(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "lake"
    root.mkdir()
    publication = publish_a_stock_reference(
        _master(),
        pd.DatetimeIndex(["2026-08-28", "2026-08-31"]),
        root=root,
        spec=_spec(),
    )

    assert publication.output_dir == (
        root
        / "cn_a_share_reference"
        / "versions"
        / "20260830"
    )
    assert publication.security_master_path.is_file()
    assert publication.trading_calendar_path.is_file()
    assert publication.manifest_path.is_file()
    assert publication.listing_count == 1
    assert publication.session_count == 2

    loaded = ParquetAStockReferenceLoader(
        context=_context(monkeypatch, root),
        connection_ref="cn_reference",
        dataset="cn_a_share_reference",
        version="20260830",
    ).load()
    assert loaded.security_master.to_frame()["ticker"].tolist() == [
        "000001"
    ]
    assert loaded.trading_calendar.tolist() == [
        pd.Timestamp("2026-08-28"),
        pd.Timestamp("2026-08-31"),
    ]


def test_identical_publication_is_idempotent_but_conflict_is_rejected(
    tmp_path: Path,
) -> None:
    root = tmp_path / "lake"
    root.mkdir()
    calendar = pd.DatetimeIndex(["2026-08-28", "2026-08-31"])

    first = publish_a_stock_reference(
        _master(), calendar, root=root, spec=_spec()
    )
    second = publish_a_stock_reference(
        _master(), calendar, root=root, spec=_spec()
    )
    assert second.content_sha256 == first.content_sha256
    assert second.output_dir == first.output_dir

    with pytest.raises(FileExistsError, match="different content"):
        publish_a_stock_reference(
            _master("000002"),
            calendar,
            root=root,
            spec=_spec(),
        )


def test_publication_rejects_duplicate_or_empty_calendar(
    tmp_path: Path,
) -> None:
    root = tmp_path / "lake"
    root.mkdir()

    with pytest.raises(ValueError, match="duplicate"):
        publish_a_stock_reference(
            _master(),
            pd.DatetimeIndex(["2026-08-28", "2026-08-28"]),
            root=root,
            spec=_spec(),
        )

    with pytest.raises(ValueError, match="empty"):
        publish_a_stock_reference(
            _master(),
            pd.DatetimeIndex([]),
            root=root,
            spec=_spec(),
        )

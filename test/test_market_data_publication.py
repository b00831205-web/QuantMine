"""Contract tests for immutable wide-frame market-data publications."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from quantmine.datareader import MarketData
from quantmine.plugins.context import SourceContext
from quantmine.plugins.contracts import (
    DataBinding,
    MarketDataBundle,
    MarketDataCapability,
)
from quantmine.plugins.sources import ParquetWideFrameDataSourcePlugin
from quantmine.storage.connections import (
    ConnectionKind,
    ConnectionRegistry,
    DataConnectionConfig,
)
from quantmine.workflows.market_data_publication import (
    MarketDataPublishSpec,
    publish_market_data_bundle,
)


def _bundle(*, close_shift: float = 0.0) -> MarketDataBundle:
    dates = pd.to_datetime(["2024-01-03", "2024-01-02"])
    close = pd.DataFrame(
        {
            "600000": [11.0 + close_shift, 10.0 + close_shift],
            "000001": [21.0 + close_shift, 20.0 + close_shift],
        },
        index=dates,
    )
    volume = pd.DataFrame(
        {
            "600000": [1_100, 1_000],
            "000001": [2_100, 2_000],
        },
        index=dates,
    )
    return MarketDataBundle(
        market=MarketData(close=close, volume=volume),
        calendar=pd.DatetimeIndex(dates),
    )


def _spec() -> MarketDataPublishSpec:
    return MarketDataPublishSpec(
        dataset_id="cn_a_share_daily_bars",
        market="CN",
        version="20260909",
        source="akshare_stock_zh_a_hist",
        frequency="daily",
        adjustment="hfq",
    )


def test_publish_market_data_bundle_writes_sorted_frames_and_manifest(
    tmp_path: Path,
) -> None:
    publication = publish_market_data_bundle(
        _bundle(),
        root=tmp_path,
        spec=_spec(),
    )

    expected_dir = (
        tmp_path
        / "cn_a_share_daily_bars"
        / "versions"
        / "20260909"
    )
    assert publication.output_dir == expected_dir
    assert publication.close_path == expected_dir / "close.parquet"
    assert publication.volume_path == expected_dir / "volume.parquet"
    assert publication.manifest_path == expected_dir / "manifest.json"
    assert publication.date_count == 2
    assert publication.ticker_count == 2
    assert len(publication.content_sha256) == 64

    close = pd.read_parquet(publication.close_path)
    volume = pd.read_parquet(publication.volume_path)
    assert close.index.tolist() == list(pd.to_datetime(["2024-01-02", "2024-01-03"]))
    assert volume.index.equals(close.index)
    assert close.columns.tolist() == ["000001", "600000"]
    assert volume.columns.equals(close.columns)

    manifest = json.loads(
        publication.manifest_path.read_text(encoding="utf-8")
    )
    assert manifest == {
        "adjustment": "hfq",
        "content_sha256": publication.content_sha256,
        "dataset_id": "cn_a_share_daily_bars",
        "date_count": 2,
        "end_date": "2024-01-03",
        "fields": ["close", "volume"],
        "frequency": "daily",
        "market": "CN",
        "schema_version": "market_data_bundle_v1",
        "source": "akshare_stock_zh_a_hist",
        "start_date": "2024-01-02",
        "ticker_count": 2,
        "version": "20260909",
    }


def test_publish_market_data_bundle_is_idempotent_for_identical_content(
    tmp_path: Path,
) -> None:
    first = publish_market_data_bundle(_bundle(), root=tmp_path, spec=_spec())
    second = publish_market_data_bundle(_bundle(), root=tmp_path, spec=_spec())

    assert second == first


def test_publish_market_data_bundle_rejects_changed_existing_version(
    tmp_path: Path,
) -> None:
    publish_market_data_bundle(_bundle(), root=tmp_path, spec=_spec())

    with pytest.raises(
        FileExistsError,
        match="already exists with different content",
    ):
        publish_market_data_bundle(
            _bundle(close_shift=1.0),
            root=tmp_path,
            spec=_spec(),
        )


def test_publish_market_data_bundle_rejects_misaligned_close_and_volume(
    tmp_path: Path,
) -> None:
    bundle = _bundle()
    misaligned = MarketDataBundle(
        market=MarketData(
            close=bundle.market.close,
            volume=bundle.market.volume.rename(columns={"600000": "600001"}),
        )
    )

    with pytest.raises(
        ValueError,
        match="close and volume must have identical dates and tickers",
    ):
        publish_market_data_bundle(
            misaligned,
            root=tmp_path,
            spec=_spec(),
        )


def test_published_version_can_be_loaded_by_existing_parquet_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    lake_root = tmp_path / "lake"
    publication = publish_market_data_bundle(
        _bundle(),
        root=lake_root,
        spec=_spec(),
    )
    monkeypatch.setenv("QUANTMINE_TEST_MARKET_DATA_ROOT", str(lake_root))
    registry = ConnectionRegistry(
        {
            "market_data_lake": DataConnectionConfig(
                kind=ConnectionKind.PARQUET,
                root_env="QUANTMINE_TEST_MARKET_DATA_ROOT",
            )
        }
    )
    plugin = ParquetWideFrameDataSourcePlugin(
        field_files={
            MarketDataCapability.CLOSE: (
                "versions/20260909/close.parquet"
            ),
            MarketDataCapability.VOLUME: (
                "versions/20260909/volume.parquet"
            ),
        }
    )
    context = SourceContext(
        connections=registry,
        run_id=1,
        artifact_dir=tmp_path / "artifacts",
    )

    loaded = plugin.load(
        DataBinding(
            connection_ref="market_data_lake",
            dataset="cn_a_share_daily_bars",
            start="2024-01-02",
            end="2024-01-02",
            tickers=("000001",),
        ),
        context,
    )

    assert publication.output_dir.is_dir()
    assert loaded.market.close.loc[
        pd.Timestamp("2024-01-02"), "000001"
    ] == 20.0
    assert loaded.market.volume.loc[
        pd.Timestamp("2024-01-02"), "000001"
    ] == 2_000
    assert loaded.calendar.equals(
        pd.DatetimeIndex([pd.Timestamp("2024-01-02")])
    )

"""Immutable same-day revision publication from staged historical repairs."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from quantmine.datareader import MarketData
from quantmine.plugins.contracts import MarketDataBundle
from quantmine.workflows.market_data_publication import (
    MarketDataPublishSpec,
    publish_market_data_bundle,
)
from quantmine.workflows.market_data_repair_publication import (
    publish_market_data_repair_revision,
)


def _base_bundle() -> MarketDataBundle:
    dates = pd.DatetimeIndex(["2024-01-02", "2024-01-03"])
    return MarketDataBundle(
        market=MarketData(
            close=pd.DataFrame(
                {"000001.SZ": [float("nan"), 11.0], "600000.SH": [float("nan"), 21.0]},
                index=dates,
            ),
            volume=pd.DataFrame(
                {"000001.SZ": [float("nan"), 110.0], "600000.SH": [float("nan"), 210.0]},
                index=dates,
            ),
        ),
        calendar=dates,
    )


def _repair_bundle() -> MarketDataBundle:
    date = pd.DatetimeIndex(["2024-01-02"])
    return MarketDataBundle(
        market=MarketData(
            close=pd.DataFrame({"000001.SZ": [10.0]}, index=date),
            volume=pd.DataFrame({"000001.SZ": [100.0]}, index=date),
        ),
        calendar=date,
    )


def _repair_bundle_filling_nothing() -> MarketDataBundle:
    """A staged repair whose values are already present in the base version."""

    date = pd.DatetimeIndex(["2024-01-03"])
    return MarketDataBundle(
        market=MarketData(
            close=pd.DataFrame({"000001.SZ": [99.0]}, index=date),
            volume=pd.DataFrame({"000001.SZ": [999.0]}, index=date),
        ),
        calendar=date,
    )


def test_repair_publication_does_not_create_a_revision_for_a_no_op_repair(
    tmp_path: Path,
) -> None:
    spec = MarketDataPublishSpec(
        dataset_id="cn_a_share_daily_bars",
        market="CN",
        version="20240103",
        source="fixture",
        frequency="daily",
        adjustment="hfq",
    )
    publish_market_data_bundle(_base_bundle(), root=tmp_path, spec=spec)

    revision = publish_market_data_repair_revision(
        root=tmp_path,
        dataset_id=spec.dataset_id,
        base_version="20240103",
        repairs=(_repair_bundle_filling_nothing(),),
    )

    assert revision.output_dir.name == "20240103"
    assert revision.content_sha256 == publish_market_data_bundle(
        _base_bundle(),
        root=tmp_path,
        spec=spec,
    ).content_sha256
    assert not (tmp_path / spec.dataset_id / "versions" / "20240103-r1").exists()


def test_repair_publication_reuses_an_identical_revision_on_a_rerun(
    tmp_path: Path,
) -> None:
    spec = MarketDataPublishSpec(
        dataset_id="cn_a_share_daily_bars",
        market="CN",
        version="20240103",
        source="fixture",
        frequency="daily",
        adjustment="hfq",
    )
    publish_market_data_bundle(_base_bundle(), root=tmp_path, spec=spec)

    first = publish_market_data_repair_revision(
        root=tmp_path,
        dataset_id=spec.dataset_id,
        base_version="20240103",
        repairs=(_repair_bundle(),),
    )
    rerun = publish_market_data_repair_revision(
        root=tmp_path,
        dataset_id=spec.dataset_id,
        base_version="20240103",
        repairs=(_repair_bundle(),),
    )

    assert first.output_dir.name == "20240103-r1"
    assert rerun.output_dir.name == "20240103-r1"
    assert rerun.content_sha256 == first.content_sha256
    assert sorted(
        path.name
        for path in (
            tmp_path / spec.dataset_id / "versions"
        ).iterdir()
        if path.is_dir()
    ) == ["20240103", "20240103-r1"]


def _second_repair_bundle() -> MarketDataBundle:
    date = pd.DatetimeIndex(["2024-01-02"])
    return MarketDataBundle(
        market=MarketData(
            close=pd.DataFrame({"600000.SH": [20.0]}, index=date),
            volume=pd.DataFrame({"600000.SH": [200.0]}, index=date),
        ),
        calendar=date,
    )


def test_repair_publication_fills_only_missing_cells_and_creates_r1(
    tmp_path: Path,
) -> None:
    spec = MarketDataPublishSpec(
        dataset_id="cn_a_share_daily_bars",
        market="CN",
        version="20240103",
        source="fixture",
        frequency="daily",
        adjustment="hfq",
    )
    base = publish_market_data_bundle(_base_bundle(), root=tmp_path, spec=spec)

    revision = publish_market_data_repair_revision(
        root=tmp_path,
        dataset_id=spec.dataset_id,
        base_version="20240103",
        repairs=(_repair_bundle(),),
    )

    assert revision.output_dir.name == "20240103-r1"
    assert pd.read_parquet(base.close_path).loc["2024-01-02", "000001.SZ"] != pd.read_parquet(base.close_path).loc["2024-01-02", "000001.SZ"]

    revised_close = pd.read_parquet(revision.close_path)
    revised_volume = pd.read_parquet(revision.volume_path)
    assert revised_close.loc["2024-01-02", "000001.SZ"] == 10.0
    assert revised_volume.loc["2024-01-02", "000001.SZ"] == 100.0
    assert revised_close.loc["2024-01-03", "600000.SH"] == 21.0


def test_repair_publication_increments_the_revision_without_overwriting_r1(
    tmp_path: Path,
) -> None:
    spec = MarketDataPublishSpec(
        dataset_id="cn_a_share_daily_bars",
        market="CN",
        version="20240103",
        source="fixture",
        frequency="daily",
        adjustment="hfq",
    )
    publish_market_data_bundle(_base_bundle(), root=tmp_path, spec=spec)
    first = publish_market_data_repair_revision(
        root=tmp_path,
        dataset_id=spec.dataset_id,
        base_version="20240103",
        repairs=(_repair_bundle(),),
    )
    second = publish_market_data_repair_revision(
        root=tmp_path,
        dataset_id=spec.dataset_id,
        base_version=first.output_dir.name,
        repairs=(_second_repair_bundle(),),
    )

    assert first.output_dir.name == "20240103-r1"
    assert second.output_dir.name == "20240103-r2"
    assert first.content_sha256 != second.content_sha256

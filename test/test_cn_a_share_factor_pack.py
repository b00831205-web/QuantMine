"""Contract tests for the first China A-share price-volume factor pack."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from quantmine.datareader import MarketData
from quantmine.plugins.bundles import get_research_bundle
from quantmine.plugins.context import SourceContext
from quantmine.plugins.contracts import (
    DataBinding,
    DataSourceComponent,
    MarketDataBundle,
    MarketDataCapability,
    PluginSpec,
    VersionedDatasetBinding,
)
from quantmine.research import run_configured_research
from quantmine.research_config import ResearchRunConfig
from quantmine.storage.connections import (
    ConnectionKind,
    ConnectionRegistry,
    DataConnectionConfig,
)


class ChinaFixtureSource:
    def load(
        self,
        binding: DataBinding,
        context: SourceContext,
    ) -> MarketDataBundle:
        del binding, context
        dates = pd.date_range("2024-01-02", periods=45, freq="B")
        return MarketDataBundle(
            market=MarketData(
                close=pd.DataFrame(
                    {
                        "000001": range(10, 55),
                        "600000": range(20, 65),
                    },
                    index=dates,
                    dtype=float,
                ),
                volume=pd.DataFrame(
                    {
                        "000001": range(1_000, 1_045),
                        "600000": range(2_000, 2_045),
                    },
                    index=dates,
                    dtype=float,
                ),
            )
        )


def create_cn_fixture_source() -> DataSourceComponent:
    return DataSourceComponent(
        id="cn_fixture_source",
        capabilities=frozenset(
            {
                MarketDataCapability.CLOSE,
                MarketDataCapability.VOLUME,
            }
        ),
        plugin=ChinaFixtureSource(),
    )


def test_default_cn_bundle_declares_the_persisted_source_and_cn_factor_pack() -> None:
    bundle = get_research_bundle("cn_a_share_v1")

    assert bundle.data_source.entry_point == (
        "quantmine.plugins.sources:create_versioned_parquet_market_data_source"
    )
    assert bundle.universe is not None
    assert bundle.universe.entry_point == (
        "quantmine.plugins.a_share:create_cn_a_share_eligibility_universe"
    )
    assert tuple(spec.entry_point for spec in bundle.factor_packs) == (
        "quantmine.plugins.builtins:create_cn_a_share_price_volume_factor_pack",
    )
    assert bundle.defaults == {
        "market": "CN",
        "currency": "CNY",
        "adjustment": "hfq",
        "storage": "versioned_parquet",
    }


def test_cn_factor_pack_runs_from_a_persisted_config_without_us_benchmark_data(
    tmp_path: Path,
) -> None:
    default_bundle = get_research_bundle("cn_a_share_v1")
    config = ResearchRunConfig(
        bundle=replace(
            default_bundle,
            data_source=PluginSpec(
                "test_cn_a_share_factor_pack:create_cn_fixture_source"
            ),
            universe=None,
        ),
        data_binding=DataBinding(
            connection_ref=None,
            dataset="fixture_cn_daily",
            start="2024-01-02",
            end="2024-03-05",
            tickers=("000001", "600000"),
            adjustment="hfq",
        ),
        factor_parameters={},
    )
    restored = ResearchRunConfig.from_snapshot(config.to_snapshot())
    context = SourceContext(
        connections=ConnectionRegistry({}),
        run_id=901,
        artifact_dir=tmp_path / "artifacts",
    )

    result = run_configured_research(
        restored,
        context,
        allowed_module_prefixes=(
            "quantmine",
            "test_cn_a_share_factor_pack",
        ),
    )

    assert result.requested_signals == (
        "CNMomentum20D",
        "CNReversal5D",
        "CNVolatility20D",
        "CNVolumeRatio20D",
        "TwentyDayVolatility",
        "TwentyDayNegVotality",
        "TwentyDayAvgVol",
        "VolPriceCorr",
    )
    assert not result.pending
    assert set(result.factors) == set(result.requested_signals)
    assert result.factors["CNMomentum20D"].iloc[-1, 0] > 0
    assert result.factors["CNReversal5D"].iloc[-1, 0] < 0
    assert result.factors["CNVolatility20D"].iloc[-1, 0] > 0
    assert result.factors["CNVolumeRatio20D"].iloc[-1, 0] > 1
    assert result.factors["TwentyDayVolatility"].iloc[-1, 0] > 0
    assert result.factors["TwentyDayAvgVol"].iloc[-1, 0] > 0


def test_default_cn_bundle_runs_from_versioned_market_and_eligibility_data(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    market_root = tmp_path / "market"
    eligibility_root = tmp_path / "eligibility"
    version_root = (
        market_root
        / "cn_a_share_daily_bars"
        / "versions"
        / "20260909"
    )
    version_root.mkdir(parents=True)
    eligibility_version_root = (
        eligibility_root
        / "cn_a_share_eligibility"
        / "versions"
        / "history_v1"
    )
    eligibility_version_root.mkdir(parents=True)

    dates = pd.date_range("2024-01-02", periods=45, freq="B")
    close = pd.DataFrame(
        {
            "000001": range(10, 55),
            "600000": range(20, 65),
        },
        index=dates,
        dtype=float,
    )
    volume = pd.DataFrame(
        {
            "000001": range(1_000, 1_045),
            "600000": range(2_000, 2_045),
        },
        index=dates,
        dtype=float,
    )
    close.to_parquet(version_root / "close.parquet")
    volume.to_parquet(version_root / "volume.parquet")

    eligibility_rows = [
        {
            "date": date,
            "ticker": ticker,
            "is_listed": True,
            "is_st": False,
            "is_suspended": False,
            "listing_days": 100,
            "is_limit_up": False,
            "is_limit_down": False,
        }
        for date in dates
        for ticker in ("000001", "600000")
    ]
    pd.DataFrame(eligibility_rows).to_parquet(
        eligibility_version_root / "eligibility.parquet"
    )

    monkeypatch.setenv("QUANTMINE_TEST_CN_MARKET_ROOT", str(market_root))
    monkeypatch.setenv(
        "QUANTMINE_TEST_CN_ELIGIBILITY_ROOT",
        str(eligibility_root),
    )
    context = SourceContext(
        connections=ConnectionRegistry(
            {
                "cn_market": DataConnectionConfig(
                    kind=ConnectionKind.PARQUET,
                    root_env="QUANTMINE_TEST_CN_MARKET_ROOT",
                ),
                "cn_eligibility": DataConnectionConfig(
                    kind=ConnectionKind.PARQUET,
                    root_env="QUANTMINE_TEST_CN_ELIGIBILITY_ROOT",
                ),
            }
        ),
        run_id=902,
        artifact_dir=tmp_path / "artifacts",
    )
    config = ResearchRunConfig.from_bundle_id(
        "cn_a_share_v1",
        DataBinding(
            connection_ref="cn_market",
            dataset="cn_a_share_daily_bars",
            version="20260909",
            start="2024-01-02",
            end="2024-03-04",
            tickers=("000001", "600000"),
            eligibility_binding=VersionedDatasetBinding(
                connection_ref="cn_eligibility",
                dataset="cn_a_share_eligibility",
                market="CN",
                version="history_v1",
            ),
        ),
    )

    result = run_configured_research(config, context)

    assert result.market_data.metadata["version"] == "20260909"
    assert result.market_data.universe is not None
    assert not result.pending
    assert set(result.factors) == set(result.requested_signals)

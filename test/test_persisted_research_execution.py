"""Tests for executing one persisted research configuration locally."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from quantmine.datareader import MarketData
from quantmine.execution import execute_persisted_research
from quantmine.plugins import builtins as builtin_plugins
from quantmine.plugins import us_equity as us_equity_plugins
from quantmine.plugins.bundles import ResearchBundle
from quantmine.plugins.context import SourceContext
from quantmine.plugins.contracts import (
    DataBinding,
    DataSourceComponent,
    FactorPackComponent,
    MarketDataBundle,
    MarketDataCapability,
    PluginSpec,
)
from quantmine.research_config import ResearchRunConfig


class InMemoryStore:
    def __init__(self, config: ResearchRunConfig) -> None:
        self.config = config

    def create(
        self,
        config: ResearchRunConfig,
        *,
        git_commit: str | None = None,
    ) -> int:
        self.config = config
        return 701

    def load(self, run_id: int) -> ResearchRunConfig:
        assert run_id == 701
        return self.config


class InMemoryPlugin:
    def load(
        self,
        binding: DataBinding,
        context: SourceContext,
    ) -> MarketDataBundle:
        dates = pd.date_range("2024-01-01", periods=5, freq="B")
        return MarketDataBundle(
            market=MarketData(
                close=pd.DataFrame(
                    {"AAA": [10.0, 11.0, 12.0, 13.0, 14.0]},
                    index=dates,
                )
            )
        )


class FixtureYFinanceSource:
    """Offline replacement that records the legacy Yahoo source request."""

    calls: list[tuple[tuple[str, ...], str, str]] = []

    def __init__(self, **_: object) -> None:
        pass

    def load(
        self,
        tickers: list[str],
        start: str,
        end: str,
    ) -> MarketData:
        type(self).calls.append((tuple(tickers), start, end))
        dates = pd.date_range("2024-01-01", periods=30, freq="B")
        close = pd.DataFrame(
            {
                "AAA": range(100, 130),
                "BBB": range(200, 230),
                "SPY": range(300, 330),
            },
            index=dates,
            dtype=float,
        )
        volume = pd.DataFrame(
            {
                "AAA": range(1_000, 1_030),
                "BBB": range(2_000, 2_030),
                "SPY": range(3_000, 3_030),
            },
            index=dates,
            dtype=float,
        )
        return MarketData(close=close, volume=volume)


def create_execution_test_source() -> DataSourceComponent:
    return DataSourceComponent(
        id="execution_test_source",
        capabilities=frozenset({MarketDataCapability.CLOSE}),
        plugin=InMemoryPlugin(),
    )


def create_execution_test_factor_pack() -> FactorPackComponent:
    return FactorPackComponent(
        id="execution_test_factor_pack",
        requires=frozenset({MarketDataCapability.CLOSE}),
        signals=("momentum",),
    )


def test_persisted_run_execution_uses_env_connections_and_configured_plugins(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("QUANTMINE_CONNECTION_TEST_CONNECTION_KIND", "parquet")
    monkeypatch.setenv("QUANTMINE_CONNECTION_TEST_CONNECTION_ROOT", str(tmp_path))

    config = ResearchRunConfig(
        bundle=ResearchBundle(
            id="execution_test_bundle",
            display_name="Execution test bundle",
            data_source=PluginSpec(
                "test_persisted_research_execution:create_execution_test_source"
            ),
            universe=None,
            factor_packs=(
                PluginSpec(
                    "test_persisted_research_execution:"
                    "create_execution_test_factor_pack"
                ),
            ),
        ),
        data_binding=DataBinding(
            connection_ref="test_connection",
            dataset="in_memory_prices",
            tickers=("AAA",),
        ),
        factor_parameters={"day": 2},
    )

    result = execute_persisted_research(
        InMemoryStore(config),
        701,
        artifact_root=tmp_path / "artifacts",
        allowed_module_prefixes=(
            "quantmine",
            "test_persisted_research_execution",
        ),
    )

    assert set(result.factors) == {"momentum"}
    assert (tmp_path / "artifacts" / "701").is_dir()


def test_default_us_bundle_runs_end_to_end_with_the_legacy_source_adapter(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """The default US bundle remains executable after config persistence.

    Yahoo Finance itself is replaced only at the network boundary.  The test
    still resolves the production bundle, uses the legacy-source adapter, and
    executes its real registered technical factors.
    """

    FixtureYFinanceSource.calls.clear()
    monkeypatch.setattr(builtin_plugins, "YFinanceSource", FixtureYFinanceSource)
    monkeypatch.setattr(us_equity_plugins, "YFinanceSource", FixtureYFinanceSource)

    original_config = ResearchRunConfig.from_bundle_id(
        "us_equity_v1",
        DataBinding(
            connection_ref=None,
            dataset="us_daily_prices",
            start="2024-01-01",
            end="2024-02-09",
            tickers=("AAA", "BBB", "SPY"),
        ),
        factor_parameters={"day": 5, "halflife": 2, "period": 3},
    )
    persisted_config = ResearchRunConfig.from_snapshot(
        original_config.to_snapshot())

    result = execute_persisted_research(
        InMemoryStore(persisted_config),
        701,
        artifact_root=tmp_path / "artifacts",
    )

    assert FixtureYFinanceSource.calls == [
        (("AAA", "BBB", "SPY"), "2024-01-01", "2024-02-09")
    ]
    assert result.requested_signals == (
        "momentum",
        "ShortTermReversal",
        "TwentyDayVolatility",
        "TwentyDayNegVotality",
        "TwentyDayAvgVol",
        "VolPriceCorr",
    )
    assert not result.pending
    assert set(result.factors) == set(result.requested_signals)
    assert (tmp_path / "artifacts" / "701").is_dir()

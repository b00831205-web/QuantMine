"""Tests for config-driven bundle resolution and factor research."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from quantmine.datareader import MarketData
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
from quantmine.plugins.loader import PluginResolutionError
from quantmine.research import run_configured_research
from quantmine.research_config import ResearchRunConfig
from quantmine.storage.connections import ConnectionRegistry


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


def create_in_memory_source() -> DataSourceComponent:
    return DataSourceComponent(
        id="in_memory",
        capabilities=frozenset({MarketDataCapability.CLOSE}),
        plugin=InMemoryPlugin(),
    )


def create_momentum_factor_pack() -> FactorPackComponent:
    return FactorPackComponent(
        id="momentum_only",
        requires=frozenset({MarketDataCapability.CLOSE}),
        signals=("momentum",),
    )


def test_configured_research_resolves_snapshot_bundle_and_computes_signals(
    tmp_path: Path,
) -> None:
    config = ResearchRunConfig(
        bundle=ResearchBundle(
            id="in_memory_bundle",
            display_name="In-memory test bundle",
            data_source=PluginSpec(
                "test_configured_research:create_in_memory_source"
            ),
            universe=None,
            factor_packs=(
                PluginSpec(
                    "test_configured_research:create_momentum_factor_pack"
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
    context = SourceContext(
        connections=ConnectionRegistry({}),
        run_id=601,
        artifact_dir=tmp_path / "artifacts",
    )

    result = run_configured_research(
        config,
        context,
        allowed_module_prefixes=("quantmine", "test_configured_research"),
    )

    assert result.requested_signals == ("momentum",)
    assert set(result.factors) == {"momentum"}
    assert result.factors["momentum"].iloc[-1, 0] == pytest.approx(1 / 13)


def test_configured_research_default_allowlist_rejects_external_plugin(
    tmp_path: Path,
) -> None:
    config = ResearchRunConfig(
        bundle=ResearchBundle(
            id="external_bundle",
            display_name="External test bundle",
            data_source=PluginSpec(
                "test_configured_research:create_in_memory_source"
            ),
            universe=None,
            factor_packs=(
                PluginSpec(
                    "test_configured_research:create_momentum_factor_pack"
                ),
            ),
        ),
        data_binding=DataBinding(
            connection_ref=None,
            dataset="in_memory_prices",
            tickers=("AAA",),
        ),
        factor_parameters={"day": 2},
    )
    context = SourceContext(
        connections=ConnectionRegistry({}),
        run_id=602,
        artifact_dir=tmp_path / "artifacts",
    )

    with pytest.raises(PluginResolutionError, match="not allowed"):
        run_configured_research(config, context)

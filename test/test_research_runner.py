"""Tests for bundle-scoped factor computation from the research data entry."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from quantmine.datareader import MarketData
from quantmine.factor_register import build_param_pool, calculate_all_factors
from quantmine.plugins.bundles import ResearchBundle, ResolvedResearchBundle
from quantmine.plugins.context import SourceContext
from quantmine.plugins.contracts import (
    DataBinding,
    DataSourceComponent,
    FactorPackComponent,
    MarketDataBundle,
    MarketDataCapability,
    PluginSpec,
)
from quantmine.research import run_factor_research
from quantmine.storage.connections import ConnectionRegistry


class StaticPlugin:
    def __init__(self, market: MarketData) -> None:
        self._market = market

    def load(
        self,
        binding: DataBinding,
        context: SourceContext,
    ) -> MarketDataBundle:
        return MarketDataBundle(market=self._market)


def _market_data() -> MarketData:
    dates = pd.date_range("2024-01-01", periods=25, freq="B")
    return MarketData(
        close=pd.DataFrame(
            {
                "AAA": range(100, 125),
                "BBB": range(200, 225),
            },
            index=dates,
            dtype=float,
        ),
        volume=pd.DataFrame(
            {
                "AAA": range(1_000, 1_025),
                "BBB": range(2_000, 2_025),
            },
            index=dates,
            dtype=float,
        ),
    )


def _binding() -> DataBinding:
    return DataBinding(
        connection_ref="test_connection",
        dataset="daily_prices",
        start="2024-01-01",
        end="2024-02-02",
        tickers=("AAA", "BBB"),
    )


def _context(tmp_path: Path) -> SourceContext:
    return SourceContext(
        connections=ConnectionRegistry({}),
        run_id=401,
        artifact_dir=tmp_path / "artifacts",
    )


def test_selected_factor_computation_includes_only_required_dependencies() -> None:
    pool = build_param_pool(
        _market_data(),
        tickers=["AAA", "BBB"],
    )

    pending, completed = calculate_all_factors(
        pool,
        factor_names=("TwentyDayVolatility",),
    )

    assert not pending
    assert set(completed) == {"daily_return", "TwentyDayVolatility"}
    assert completed["TwentyDayVolatility"] is not None


def test_selected_factor_computation_rejects_unknown_factor_names() -> None:
    with pytest.raises(ValueError, match="Unknown factor"):
        calculate_all_factors(
            build_param_pool(_market_data(), tickers=["AAA", "BBB"]),
            factor_names=("does_not_exist",),
        )


def test_research_runner_loads_bundle_data_and_returns_only_pack_signals(
    tmp_path: Path,
) -> None:
    data_source = DataSourceComponent(
        id="in_memory",
        capabilities=frozenset(
            {
                MarketDataCapability.CLOSE,
                MarketDataCapability.VOLUME,
            }
        ),
        plugin=StaticPlugin(_market_data()),
    )
    factor_pack = FactorPackComponent(
        id="momentum_only",
        requires=frozenset({MarketDataCapability.CLOSE}),
        signals=("momentum",),
    )
    resolved = ResolvedResearchBundle(
        definition=ResearchBundle(
            id="test_bundle",
            display_name="Test bundle",
            data_source=PluginSpec("test:source"),
            universe=None,
            factor_packs=(PluginSpec("test:pack"),),
        ),
        data_source=data_source,
        universe=None,
        factor_packs=(factor_pack,),
    )

    result = run_factor_research(
        resolved,
        _binding(),
        _context(tmp_path),
        factor_parameters={"day": 2},
    )

    assert not result.pending
    assert result.requested_signals == ("momentum",)
    assert set(result.factors) == {"momentum"}
    assert result.factors["momentum"].shape == (25, 2)


def test_research_runner_rejects_an_unknown_pack_signal(tmp_path: Path) -> None:
    data_source = DataSourceComponent(
        id="in_memory",
        capabilities=frozenset({MarketDataCapability.CLOSE}),
        plugin=StaticPlugin(_market_data()),
    )
    factor_pack = FactorPackComponent(
        id="invalid_pack",
        requires=frozenset({MarketDataCapability.CLOSE}),
        signals=("does_not_exist",),
    )
    resolved = ResolvedResearchBundle(
        definition=ResearchBundle(
            id="invalid_bundle",
            display_name="Invalid bundle",
            data_source=PluginSpec("test:source"),
            universe=None,
            factor_packs=(PluginSpec("test:pack"),),
        ),
        data_source=data_source,
        universe=None,
        factor_packs=(factor_pack,),
    )

    with pytest.raises(ValueError, match="Unknown factor"):
        run_factor_research(
            resolved,
            _binding(),
            _context(tmp_path),
        )

"""Tests for applying a point-in-time universe before factor calculation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from quantmine import factor_mining
from quantmine.datareader import MarketData
from quantmine.plugins.bundles import ResearchBundle, ResolvedResearchBundle
from quantmine.plugins.context import SourceContext
from quantmine.plugins.contracts import (
    DataBinding,
    DataSourceComponent,
    FactorPackComponent,
    MarketDataBundle,
    MarketDataCapability,
    PluginSpec,
    UniverseComponent,
)
from quantmine.research import _apply_universe, run_factor_research
from quantmine.storage.connections import ConnectionRegistry

_ = factor_mining


class StaticMarketPlugin:
    def __init__(self, market: MarketData) -> None:
        self.market = market

    def load(
        self,
        binding: DataBinding,
        context: SourceContext,
    ) -> MarketDataBundle:
        del binding, context
        return MarketDataBundle(market=self.market)


class ScheduledMembership:
    def __init__(self, first_date: pd.Timestamp, second_date: pd.Timestamp) -> None:
        self.first_date = first_date
        self.second_date = second_date

    def get_constituents(self, date: pd.Timestamp) -> set[str]:
        if date <= self.first_date:
            return {"AAA"}
        if date >= self.second_date:
            return {"BBB"}
        return set()


class FixtureUniversePlugin:
    def __init__(self, membership: ScheduledMembership) -> None:
        self.membership = membership

    def load(
        self,
        binding: DataBinding,
        context: SourceContext,
    ) -> ScheduledMembership:
        del binding, context
        return self.membership


class StatusAwareMembership(ScheduledMembership):
    """Universe with market-specific execution state kept as a sidecar."""

    def __init__(self, first_date: pd.Timestamp, second_date: pd.Timestamp) -> None:
        super().__init__(first_date, second_date)
        self.status_calls = 0

    def status_on(self, date: pd.Timestamp, ticker: str) -> dict[str, bool]:
        self.status_calls += 1
        return {
            "is_limit_up": ticker == "AAA",
            "is_limit_down": False,
            "is_st": False,
        }


def test_runtime_universe_masks_each_market_field_by_date_and_membership(
    tmp_path: Path,
) -> None:
    dates = pd.date_range("2024-01-02", periods=5, freq="B")
    market = MarketData(
        close=pd.DataFrame(
            {"AAA": [10.0, 11.0, 12.0, 13.0, 14.0],
             "BBB": [20.0, 21.0, 22.0, 23.0, 24.0]},
            index=dates,
        ),
        volume=pd.DataFrame(
            {"AAA": [100.0, 110.0, 120.0, 130.0, 140.0],
             "BBB": [200.0, 210.0, 220.0, 230.0, 240.0]},
            index=dates,
        ),
    )
    membership = ScheduledMembership(dates[1], dates[3])
    resolved = ResolvedResearchBundle(
        definition=ResearchBundle(
            id="scheduled_universe_bundle",
            display_name="Scheduled membership test",
            data_source=PluginSpec("test:source"),
            universe=PluginSpec("test:universe"),
            factor_packs=(PluginSpec("test:pack"),),
        ),
        data_source=DataSourceComponent(
            id="static_market",
            capabilities=frozenset({
                MarketDataCapability.CLOSE,
                MarketDataCapability.VOLUME,
            }),
            plugin=StaticMarketPlugin(market),
        ),
        universe=UniverseComponent(
            id="scheduled_membership",
            plugin=FixtureUniversePlugin(membership),
        ),
        factor_packs=(
            FactorPackComponent(
                id="momentum_only",
                requires=frozenset({MarketDataCapability.CLOSE}),
                signals=("momentum",),
            ),
        ),
    )
    context = SourceContext(
        connections=ConnectionRegistry({}),
        run_id=1001,
        artifact_dir=tmp_path / "artifacts",
    )

    result = run_factor_research(
        resolved,
        DataBinding(
            connection_ref=None,
            dataset="fixture_prices",
            tickers=("AAA", "BBB"),
        ),
        context,
    )

    assert result.market_data.universe is membership
    assert result.market_data.market.close.loc[dates[0], "AAA"] == 10.0
    assert pd.isna(result.market_data.market.close.loc[dates[0], "BBB"])
    assert pd.isna(result.market_data.market.close.loc[dates[2], "AAA"])
    assert pd.isna(result.market_data.market.close.loc[dates[2], "BBB"])
    assert pd.isna(result.market_data.market.volume.loc[dates[4], "AAA"])
    assert result.market_data.market.volume.loc[dates[4], "BBB"] == 240.0


def test_status_extensions_remain_on_the_universe_sidecar() -> None:
    dates = pd.date_range("2024-01-02", periods=2, freq="B")
    universe = StatusAwareMembership(dates[0], dates[1])
    bundle = MarketDataBundle(
        market=MarketData(
            close=pd.DataFrame(
                {"AAA": [10.0, 11.0], "BBB": [20.0, 21.0]},
                index=dates,
            ),
            volume=pd.DataFrame(
                {"AAA": [100.0, 110.0], "BBB": [200.0, 210.0]},
                index=dates,
            ),
        )
    )

    projected = _apply_universe(bundle, universe)

    assert set(vars(projected.market)) == {"close", "volume", "market_cap"}
    assert projected.universe is universe
    assert universe.status_calls == 0

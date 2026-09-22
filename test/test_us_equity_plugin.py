"""Compatibility tests for the first-class US-equity market plugin."""

from __future__ import annotations

from quantmine.plugins import builtins
from quantmine.plugins.bundles import get_research_bundle
from quantmine.plugins.us_equity import (
    create_sp500_universe,
    create_us_technical_factor_pack,
    create_yfinance_data_source,
)


def test_default_us_bundle_uses_the_dedicated_market_plugin_entry_points() -> None:
    bundle = get_research_bundle("us_equity_v1")

    assert bundle.data_source.entry_point == (
        "quantmine.plugins.us_equity:create_yfinance_data_source"
    )
    assert bundle.universe is not None
    assert bundle.universe.entry_point == (
        "quantmine.plugins.us_equity:create_sp500_universe"
    )
    assert bundle.factor_packs[0].entry_point == (
        "quantmine.plugins.us_equity:create_us_technical_factor_pack"
    )


def test_legacy_builtin_factories_remain_compatible_with_the_market_plugin() -> None:
    assert builtins.create_yfinance_data_source().id == (
        create_yfinance_data_source().id
    )
    assert builtins.create_sp500_universe().id == create_sp500_universe().id
    assert builtins.create_us_technical_factor_pack().signals == (
        create_us_technical_factor_pack().signals
    )

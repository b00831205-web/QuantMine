"""Contract tests for composable research bundles.

These tests define the first plugin-layer acceptance criteria without changing
the current data download, factor formulas, IC mathematics, or Airflow DAG.
"""

from __future__ import annotations

import pytest

from quantmine.datareader import YFinanceSource
from quantmine.plugins import (
    DataSourceComponent,
    MarketDataCapability,
    PluginResolutionError,
    PluginSpec,
    get_research_bundle,
    resolve_plugin,
    resolve_research_bundle,
)


def create_close_only_source() -> DataSourceComponent:
    """Test plugin factory loaded through the standard import-path mechanism."""

    return DataSourceComponent(
        id="close_only",
        source=YFinanceSource(),
        capabilities=frozenset({MarketDataCapability.CLOSE}),
    )


def test_default_us_bundle_resolves_without_network_access():
    bundle = resolve_research_bundle("us_equity_v1")

    assert bundle.data_source.id == "yfinance"
    assert bundle.universe is not None
    assert bundle.universe.id == "sp500_membership"
    assert bundle.definition.defaults["benchmark_ticker"] == "SPY"
    assert bundle.factor_packs[0].id == "us_technical_v1"
    assert MarketDataCapability.CLOSE in bundle.data_source.capabilities
    assert MarketDataCapability.VOLUME in bundle.data_source.capabilities


def test_bundle_override_rejects_factor_pack_missing_required_data():
    with pytest.raises(
        PluginResolutionError,
        match="requires unavailable data: volume",
    ):
        resolve_research_bundle(
            "us_equity_v1",
            data_source_override=PluginSpec(
                "test_research_bundles:create_close_only_source"
            ),
            allowed_module_prefixes=("quantmine", "test_research_bundles"),
        )


def test_plugin_resolution_requires_allow_list_match():
    with pytest.raises(PluginResolutionError, match="is not allowed"):
        resolve_plugin(
            PluginSpec(
                "quantmine.plugins.builtins:create_yfinance_data_source"
            ),
            allowed_module_prefixes=("local_plugins",),
        )


def test_plugin_allow_list_uses_module_boundaries():
    with pytest.raises(PluginResolutionError, match="is not allowed"):
        resolve_plugin(
            PluginSpec("quantmine_evil.plugin:create_source"),
            allowed_module_prefixes=("quantmine",),
        )


def test_plugin_allow_list_rejects_a_bare_string():
    with pytest.raises(TypeError, match="not a string"):
        resolve_plugin(
            PluginSpec(
                "quantmine.plugins.builtins:create_yfinance_data_source"
            ),
            allowed_module_prefixes="quantmine",  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "prefix",
    ("", " quantmine", "quantmine ", "quantmine..plugins", "quantmine-plugin"),
)
def test_plugin_allow_list_rejects_invalid_module_prefix(prefix: str):
    with pytest.raises(ValueError, match="valid trimmed module names"):
        resolve_plugin(
            PluginSpec(
                "quantmine.plugins.builtins:create_yfinance_data_source"
            ),
            allowed_module_prefixes=(prefix,),
        )


def test_plugin_resolution_wraps_missing_module_import_error():
    with pytest.raises(
        PluginResolutionError,
        match="plugin module 'missing_quantmine_plugin' could not be imported",
    ) as raised:
        resolve_plugin(
            PluginSpec("missing_quantmine_plugin:create_source"),
            allowed_module_prefixes=("missing_quantmine_plugin",),
        )

    assert isinstance(raised.value.__cause__, ImportError)


def test_plugin_resolution_reports_missing_factory_separately():
    with pytest.raises(
        PluginResolutionError,
        match="factory 'missing_factory' was not found",
    ) as raised:
        resolve_plugin(
            PluginSpec("quantmine.plugins.builtins:missing_factory"),
            allowed_module_prefixes=("quantmine",),
        )

    assert isinstance(raised.value.__cause__, AttributeError)


def test_unknown_bundle_lists_available_bundle_ids():
    with pytest.raises(PluginResolutionError, match="us_equity_v1"):
        get_research_bundle("not_a_bundle")

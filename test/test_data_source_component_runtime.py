"""Tests for the research entry point of DataSourceComponent."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from quantmine.datareader import MarketData
from quantmine.plugins.context import SourceContext
from quantmine.plugins.contracts import (
    DataBinding,
    DataSourceComponent,
    MarketDataBundle,
    MarketDataCapability,
)
from quantmine.plugins.runtime import load_data_source_component
from quantmine.storage.connections import ConnectionRegistry


class StaticPlugin:
    def __init__(self, bundle: MarketDataBundle) -> None:
        self.bundle = bundle
        self.binding: DataBinding | None = None

    def load(
        self,
        binding: DataBinding,
        context: SourceContext,
    ) -> MarketDataBundle:
        self.binding = binding
        return self.bundle


class StaticLegacySource:
    def load(self, tickers: list[str], start: str, end: str) -> MarketData:
        return MarketData(
            close=pd.DataFrame(
                {ticker: [1.0] for ticker in tickers},
                index=pd.to_datetime([start]),
            )
        )


def _context(tmp_path: Path) -> SourceContext:
    return SourceContext(
        connections=ConnectionRegistry({}),
        run_id=301,
        artifact_dir=tmp_path / "artifacts",
    )


def _binding(**overrides: object) -> DataBinding:
    values: dict[str, object] = {
        "connection_ref": "cn_equity_lake",
        "dataset": "daily_prices",
        "start": "2024-01-02",
        "end": "2024-01-03",
        "tickers": ("AAA",),
    }
    values.update(overrides)
    return DataBinding(**values)


def test_runtime_entry_loads_a_data_source_plugin(tmp_path: Path) -> None:
    expected = MarketDataBundle(
        market=MarketData(
            close=pd.DataFrame(
                {"AAA": [10.0]},
                index=pd.to_datetime(["2024-01-02"]),
            )
        )
    )
    plugin = StaticPlugin(expected)
    component = DataSourceComponent(
        id="static",
        capabilities=frozenset({MarketDataCapability.CLOSE}),
        plugin=plugin,
        connection_ref="cn_equity_lake",
    )

    actual = load_data_source_component(
        component,
        _binding(),
        _context(tmp_path),
    )

    assert actual is expected
    assert plugin.binding == _binding()


def test_runtime_entry_adapts_a_legacy_data_source(tmp_path: Path) -> None:
    component = DataSourceComponent(
        id="legacy",
        capabilities=frozenset({MarketDataCapability.CLOSE}),
        source=StaticLegacySource(),
    )

    actual = load_data_source_component(
        component,
        _binding(),
        _context(tmp_path),
    )

    assert actual.market.close.loc[pd.Timestamp("2024-01-02"), "AAA"] == 1.0
    assert actual.metadata["source_kind"] == "legacy"


def test_runtime_entry_rejects_component_binding_connection_mismatch(
    tmp_path: Path,
) -> None:
    component = DataSourceComponent(
        id="locked_source",
        capabilities=frozenset({MarketDataCapability.CLOSE}),
        plugin=StaticPlugin(MarketDataBundle(market=MarketData())),
        connection_ref="approved_connection",
    )

    with pytest.raises(ValueError, match="requires connection_ref"):
        load_data_source_component(
            component,
            _binding(connection_ref="other_connection"),
            _context(tmp_path),
        )


def test_runtime_entry_rejects_a_plugin_that_lies_about_capabilities(
    tmp_path: Path,
) -> None:
    component = DataSourceComponent(
        id="invalid_source",
        capabilities=frozenset({MarketDataCapability.CLOSE}),
        plugin=StaticPlugin(MarketDataBundle(market=MarketData())),
    )

    with pytest.raises(ValueError, match="MarketDataBundle: close"):
        load_data_source_component(
            component,
            _binding(),
            _context(tmp_path),
        )

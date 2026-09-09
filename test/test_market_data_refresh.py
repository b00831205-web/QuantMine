"""Tests for source-neutral market-data materialization."""

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
from quantmine.storage.connections import (
    ConnectionKind,
    ConnectionRegistry,
    DataConnectionConfig,
)
from quantmine.workflows.market_data_publication import MarketDataPublishSpec
from quantmine.workflows.market_data_refresh import refresh_market_data


class RecordingSource:
    def __init__(self) -> None:
        self.calls: list[tuple[DataBinding, SourceContext]] = []

    def load(
        self,
        binding: DataBinding,
        context: SourceContext,
    ) -> MarketDataBundle:
        self.calls.append((binding, context))
        dates = pd.to_datetime(["2024-01-02", "2024-01-03"])
        return MarketDataBundle(
            market=MarketData(
                close=pd.DataFrame(
                    {"000001": [10.0, 11.0]},
                    index=dates,
                ),
                volume=pd.DataFrame(
                    {"000001": [1_000, 1_100]},
                    index=dates,
                ),
            )
        )


def _component(plugin: RecordingSource) -> DataSourceComponent:
    return DataSourceComponent(
        id="recording_source",
        capabilities=frozenset(
            {
                MarketDataCapability.CLOSE,
                MarketDataCapability.VOLUME,
            }
        ),
        plugin=plugin,
    )


def _binding() -> DataBinding:
    return DataBinding(
        connection_ref=None,
        dataset="provider_request",
        start="2024-01-02",
        end="2024-01-03",
        tickers=("000001",),
        adjustment="hfq",
    )


def _spec() -> MarketDataPublishSpec:
    return MarketDataPublishSpec(
        dataset_id="cn_a_share_daily_bars",
        market="CN",
        version="20260909",
        source="fixture",
        frequency="daily",
        adjustment="hfq",
    )


def _context(
    tmp_path: Path,
    *,
    read_only: bool,
) -> SourceContext:
    root = tmp_path / "lake"
    root.mkdir()
    registry = ConnectionRegistry(
        {
            "market_data_output": DataConnectionConfig(
                kind=ConnectionKind.PARQUET,
                root_env="QUANTMINE_TEST_REFRESH_ROOT",
                read_only=read_only,
            )
        }
    )
    return SourceContext(
        connections=registry,
        run_id=101,
        artifact_dir=tmp_path / "artifacts",
    )


def test_refresh_market_data_loads_component_and_publishes_version(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "lake"
    monkeypatch.setenv("QUANTMINE_TEST_REFRESH_ROOT", str(root))
    context = _context(tmp_path, read_only=False)
    source = RecordingSource()
    binding = _binding()

    publication = refresh_market_data(
        context,
        source_component=_component(source),
        binding=binding,
        output_connection_ref="market_data_output",
        publish_spec=_spec(),
    )

    assert source.calls == [(binding, context)]
    assert publication.output_dir == (
        root
        / "cn_a_share_daily_bars"
        / "versions"
        / "20260909"
    )
    assert publication.date_count == 2
    assert publication.ticker_count == 1


def test_refresh_market_data_rejects_read_only_output_before_loading_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "lake"
    monkeypatch.setenv("QUANTMINE_TEST_REFRESH_ROOT", str(root))
    context = _context(tmp_path, read_only=True)
    source = RecordingSource()

    with pytest.raises(
        PermissionError,
        match="market_data_output.*read-only",
    ):
        refresh_market_data(
            context,
            source_component=_component(source),
            binding=_binding(),
            output_connection_ref="market_data_output",
            publish_spec=_spec(),
        )

    assert source.calls == []

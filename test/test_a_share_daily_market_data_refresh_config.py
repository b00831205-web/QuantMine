"""Tests for persisted, date-resolved A-share cumulative refresh config."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from quantmine.plugins.context import SourceContext
from quantmine.plugins.contracts import DataSourceComponent, PluginSpec
from quantmine.storage.connections import ConnectionRegistry
from quantmine.workflows.a_share_market_data_refresh import (
    AStockDailyMarketDataRefreshConfig,
    resolve_a_share_daily_market_data_refresh_config,
    run_configured_a_share_cumulative_refresh,
)


def _payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "source": {
            "entry_point": (
                "quantmine.plugins.akshare:"
                "create_akshare_a_stock_data_source"
            ),
            "params": {"default_adjustment": "hfq"},
        },
        "binding": {
            "connection_ref": None,
            "dataset": "akshare_a_share_history",
            "start": "{as_of_date}",
            "end": "{as_of_date}",
            "adjustment": "hfq",
            "metadata": {},
        },
        "reference_binding": {
            "connection_ref": "cn_reference",
            "dataset": "cn_a_share_reference",
            "market": "CN",
            "version": "{as_of_date}",
        },
        "output_connection_ref": "cn_market_data",
        "publication": {
            "dataset_id": "cn_a_share_daily_bars",
            "market": "CN",
            "version": "{as_of_date}",
            "source": "akshare_stock_zh_a_hist",
            "frequency": "daily",
            "adjustment": "hfq",
            "schema_version": "market_data_bundle_v1",
        },
        "policy": {
            "batch_size": 50,
            "max_retries": 3,
            "checkpoint_connection_ref": "cn_market_checkpoint",
            "resume": True,
        },
    }


def test_daily_refresh_config_round_trips_date_selectors() -> None:
    config = AStockDailyMarketDataRefreshConfig.from_mapping(_payload())

    assert config.binding.tickers == ()
    assert config.binding.start == "{as_of_date}"
    assert config.reference_binding.version == "{as_of_date}"
    assert config.publication.version == "{as_of_date}"
    assert config.to_mapping() == _payload()


def test_daily_refresh_config_resolves_all_run_date_selectors() -> None:
    config = AStockDailyMarketDataRefreshConfig.from_mapping(_payload())

    resolved = resolve_a_share_daily_market_data_refresh_config(
        config,
        as_of_date="2024-01-03",
    )

    assert resolved.binding.start == "2024-01-03"
    assert resolved.binding.end == "2024-01-03"
    assert resolved.reference_binding.version == "20240103"
    assert resolved.publication.version == "20240103"


@pytest.mark.parametrize(
    "path, value",
    [
        (("binding", "start"), "2024-01-02"),
        (("binding", "end"), "2024-01-02"),
        (("reference_binding", "version"), "reference_v1"),
        (("publication", "version"), "bars_v1"),
    ],
)
def test_daily_refresh_config_rejects_fixed_or_partial_date_selectors(
    path: tuple[str, str],
    value: str,
) -> None:
    payload = _payload()
    section = dict(payload[path[0]])
    section[path[1]] = value
    payload[path[0]] = section

    with pytest.raises(ValueError, match="as_of_date|daily"):
        AStockDailyMarketDataRefreshConfig.from_mapping(payload)


def test_configured_daily_refresh_resolves_plugin_and_dispatches(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = AStockDailyMarketDataRefreshConfig.from_mapping(_payload())
    context = SourceContext(
        connections=ConnectionRegistry({}),
        run_id=301,
        artifact_dir=tmp_path / "artifacts",
    )
    component = DataSourceComponent(
        id="configured_daily_source",
        capabilities=frozenset(),
        plugin=object(),
    )
    publication = SimpleNamespace(name="publication")
    dispatched: list[dict[str, object]] = []

    from quantmine.workflows import a_share_market_data_refresh as module

    monkeypatch.setattr(module, "resolve_plugin", lambda *args, **kwargs: component)

    def fake_refresh(context_arg, **kwargs):
        dispatched.append({"context": context_arg, **kwargs})
        return publication

    monkeypatch.setattr(
        module,
        "refresh_a_share_cumulative_market_data",
        fake_refresh,
    )

    result = run_configured_a_share_cumulative_refresh(
        context,
        config=config,
        as_of_date="2024-01-03",
        allowed_module_prefixes=("quantmine",),
    )

    assert result is publication
    assert len(dispatched) == 1
    call = dispatched[0]
    assert call["context"] is context
    assert call["source_component"] is component
    assert call["output_connection_ref"] == "cn_market_data"
    assert call["policy"] is config.policy
    assert call["binding"].start == "2024-01-03"
    assert call["binding"].end == "2024-01-03"
    assert call["reference_binding"].version == "20240103"
    assert call["publish_spec"].version == "20240103"

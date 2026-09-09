"""Tests for persisted one-off A-share history refresh configuration."""

from __future__ import annotations

from pathlib import Path

import pytest

from quantmine.a_share_history_loader import (
    load_a_share_history_refresh_config,
)
from quantmine.workflows.a_share_market_data_refresh import (
    AStockHistoryRefreshConfig,
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
            "start": "2020-01-01",
            "end": "2026-09-09",
            "adjustment": "hfq",
            "metadata": {},
        },
        "reference_binding": {
            "connection_ref": "cn_reference",
            "dataset": "cn_a_share_reference",
            "market": "CN",
            "version": "20260906",
        },
        "output_connection_ref": "cn_market_data",
        "publication": {
            "dataset_id": "cn_a_share_daily_bars",
            "market": "CN",
            "version": "20260909",
            "source": "akshare_stock_zh_a_hist",
            "frequency": "daily",
            "adjustment": "hfq",
            "schema_version": "market_data_bundle_v1",
        },
    }


def test_history_refresh_config_round_trips_without_persisting_tickers() -> None:
    config = AStockHistoryRefreshConfig.from_mapping(_payload())

    assert config.binding.tickers == ()
    assert config.binding.start == "2020-01-01"
    assert config.binding.end == "2026-09-09"
    assert config.source.params == {"default_adjustment": "hfq"}
    assert config.to_mapping() == _payload()


def test_history_refresh_config_loads_from_top_level_yaml(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
a_share_history_refresh:
  schema_version: 1
  source:
    entry_point: quantmine.plugins.akshare:create_akshare_a_stock_data_source
    params:
      default_adjustment: hfq
  binding:
    connection_ref: null
    dataset: akshare_a_share_history
    start: '2020-01-01'
    end: '2026-09-09'
    adjustment: hfq
    metadata: {}
  reference_binding:
    connection_ref: cn_reference
    dataset: cn_a_share_reference
    market: CN
    version: '20260906'
  output_connection_ref: cn_market_data
  publication:
    dataset_id: cn_a_share_daily_bars
    market: CN
    version: '20260909'
    source: akshare_stock_zh_a_hist
    frequency: daily
    adjustment: hfq
    schema_version: market_data_bundle_v1
""".lstrip(),
        encoding="utf-8",
    )

    config = load_a_share_history_refresh_config(config_path)

    assert config.to_mapping() == _payload()


def test_history_refresh_config_rejects_inconsistent_adjustment() -> None:
    payload = _payload()
    publication = dict(payload["publication"])
    publication["adjustment"] = "qfq"
    payload["publication"] = publication

    with pytest.raises(
        ValueError,
        match="publication.adjustment must match binding.adjustment",
    ):
        AStockHistoryRefreshConfig.from_mapping(payload)

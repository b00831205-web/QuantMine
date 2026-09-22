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
from quantmine.workflows.market_data_refresh import MarketDataRefreshPolicy


def _payload() -> dict[str, object]:
    return {
        "schema_version": 2,
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
        "policy": {
            "batch_size": 50,
            "max_retries": 3,
            "checkpoint_connection_ref": None,
            "resume": True,
        },
    }


def test_history_refresh_config_round_trips_without_persisting_tickers() -> None:
    config = AStockHistoryRefreshConfig.from_mapping(_payload())

    assert config.binding.tickers == ()
    assert config.binding.start == "2020-01-01"
    assert config.binding.end == "2026-09-09"
    assert config.source.params == {"default_adjustment": "hfq"}
    assert config.policy == MarketDataRefreshPolicy()
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


def test_example_history_refresh_enables_throttling_and_long_retry_backoff() -> None:
    example_path = Path(__file__).parents[1] / "config.example.yaml"

    config = load_a_share_history_refresh_config(example_path)

    assert config.source.params == {
        "default_adjustment": "hfq",
        "request_interval_seconds": 0.5,
        "retry_policy": {
            "attempts": 6,
            "initial_delay_seconds": 15.0,
            "backoff_multiplier": 2.0,
            "max_delay_seconds": 120.0,
        },
    }
    assert config.policy == MarketDataRefreshPolicy(
        batch_size=5,
        max_retries=0,
        checkpoint_connection_ref="cn_market_checkpoint",
        resume=True,
    )
    assert config.publication.source == "akshare_routed_history"


def test_history_refresh_config_round_trips_custom_policy() -> None:
    payload = _payload()
    payload["policy"] = {
        "batch_size": 25,
        "max_retries": 5,
        "checkpoint_connection_ref": "cn_market_checkpoint",
        "resume": False,
    }

    config = AStockHistoryRefreshConfig.from_mapping(payload)

    assert config.policy == MarketDataRefreshPolicy(
        batch_size=25,
        max_retries=5,
        checkpoint_connection_ref="cn_market_checkpoint",
        resume=False,
    )
    assert config.to_mapping() == payload


@pytest.mark.parametrize(
    ("field", "value", "error_type"),
    [
        ("batch_size", "50", TypeError),
        ("batch_size", 0, ValueError),
        ("max_retries", True, TypeError),
        ("max_retries", -1, ValueError),
        ("checkpoint_connection_ref", " checkpoint", TypeError),
        ("resume", 1, TypeError),
    ],
)
def test_history_refresh_config_rejects_invalid_policy(
    field: str,
    value: object,
    error_type: type[Exception],
) -> None:
    payload = _payload()
    policy = dict(payload["policy"])
    policy[field] = value
    payload["policy"] = policy

    with pytest.raises(error_type, match=f"policy\\.{field}|{field}"):
        AStockHistoryRefreshConfig.from_mapping(payload)


def test_history_refresh_config_rejects_unknown_schema_version() -> None:
    payload = _payload()
    payload["schema_version"] = 3

    with pytest.raises(ValueError, match="schema version 3"):
        AStockHistoryRefreshConfig.from_mapping(payload)


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

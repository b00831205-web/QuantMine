"""Tests for the non-secret A-share daily production-pipeline config."""

from __future__ import annotations

import json

import pytest

from quantmine.workflows.a_share_daily_pipeline import (
    AStockDailyPipelineConfig,
)


def _payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "raw_connection_ref": "cn_raw_lake",
        "reference_binding": {
            "connection_ref": "cn_reference_lake",
            "dataset": "cn_a_share_reference",
            "market": "CN",
            "version": "20260830",
        },
        "status_binding": {
            "connection_ref": "cn_status_lake",
            "dataset": "daily_market_status",
            "market": "CN",
            "version": "history_v1",
        },
        "eligibility_binding": {
            "connection_ref": "cn_eligibility_lake",
            "dataset": "cn_daily_eligibility",
            "market": "CN",
            "version": "history_v1",
        },
        "eligibility_rule_version": "cn_eligibility_rules_v1",
    }


def test_pipeline_config_round_trips_as_safe_json() -> None:
    config = AStockDailyPipelineConfig.from_mapping(_payload())

    snapshot = config.to_mapping()
    serialized = json.dumps(snapshot, sort_keys=True, allow_nan=False)

    assert json.loads(serialized) == _payload()
    assert config.status_binding.dataset == "daily_market_status"
    assert config.eligibility_rule_version == "cn_eligibility_rules_v1"


def test_pipeline_config_rejects_a_non_cn_binding() -> None:
    payload = _payload()
    payload["status_binding"] = {
        **payload["status_binding"],
        "market": "US",
    }

    with pytest.raises(ValueError, match="status_binding.market must be 'CN'"):
        AStockDailyPipelineConfig.from_mapping(payload)

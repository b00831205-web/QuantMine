"""Serializable market-pipeline topology definitions for the DAG factory."""

from __future__ import annotations

import json

import pytest

from quantmine.market_pipeline_config import (
    MARKET_PIPELINE_CONFIG_VERSION,
    MarketPipelineDefinition,
    PipelineStageDefinition,
    PipelineStageKind,
)
from quantmine.plugins.contracts import PluginSpec


def _definition() -> MarketPipelineDefinition:
    return MarketPipelineDefinition(
        id="cn_a_share_research",
        dag_id="quantmine_cn_a_share_research",
        display_name="CN A-share daily research",
        schedule="0 18 * * 1-5",
        connection_refs=(
            "cn_raw_lake",
            "cn_reference_lake",
            "cn_status_lake",
            "cn_eligibility_lake",
        ),
        stages=(
            PipelineStageDefinition(
                id="session_gate",
                plugin=PluginSpec("quantmine.pipeline_stages:session_gate"),
                kind=PipelineStageKind.SESSION_GATE,
            ),
            PipelineStageDefinition(
                id="production",
                plugin=PluginSpec("quantmine.pipeline_stages:production"),
                upstream=("session_gate",),
            ),
            PipelineStageDefinition(
                id="factor_research",
                plugin=PluginSpec("quantmine.pipeline_stages:factor_research"),
                upstream=("production",),
            ),
            PipelineStageDefinition(
                id="ic_validation",
                plugin=PluginSpec("quantmine.pipeline_stages:ic_validation"),
                upstream=("factor_research",),
            ),
            PipelineStageDefinition(
                id="backtest",
                plugin=PluginSpec("quantmine.pipeline_stages:backtest"),
                upstream=("ic_validation",),
            ),
        ),
        metadata={"market": "CN", "timezone": "Asia/Shanghai"},
    )


def test_definition_round_trips_as_json_and_preserves_stage_order() -> None:
    definition = _definition()

    snapshot = definition.to_snapshot()
    restored = MarketPipelineDefinition.from_snapshot(
        json.loads(json.dumps(snapshot, sort_keys=True, allow_nan=False)),
    )

    assert snapshot["schema_version"] == MARKET_PIPELINE_CONFIG_VERSION
    assert restored == definition
    assert restored.ordered_stage_ids == (
        "session_gate",
        "production",
        "factor_research",
        "ic_validation",
        "backtest",
    )
    assert restored.connection_refs == (
        "cn_raw_lake",
        "cn_reference_lake",
        "cn_status_lake",
        "cn_eligibility_lake",
    )
    assert restored.stages[0].kind is PipelineStageKind.SESSION_GATE


def test_definition_supports_fan_out_and_fan_in() -> None:
    definition = MarketPipelineDefinition(
        id="multi_market",
        dag_id="quantmine_multi_market",
        display_name="Multi-market research",
        schedule="0 0 * * *",
        stages=(
            PipelineStageDefinition(
                id="us_production",
                plugin=PluginSpec("quantmine.pipeline_stages:production"),
            ),
            PipelineStageDefinition(
                id="cn_production",
                plugin=PluginSpec("quantmine.pipeline_stages:production"),
            ),
            PipelineStageDefinition(
                id="combined_research",
                plugin=PluginSpec("quantmine.pipeline_stages:research"),
                upstream=("us_production", "cn_production"),
            ),
        ),
    )

    assert definition.ordered_stage_ids == (
        "us_production",
        "cn_production",
        "combined_research",
    )


@pytest.mark.parametrize(
    ("stages", "message"),
    [
        (
            (
                PipelineStageDefinition(
                    id="research",
                    plugin=PluginSpec("quantmine.pipeline_stages:research"),
                    upstream=("missing",),
                ),
            ),
            "unknown upstream",
        ),
        (
            (
                PipelineStageDefinition(
                    id="first",
                    plugin=PluginSpec("quantmine.pipeline_stages:first"),
                    upstream=("second",),
                ),
                PipelineStageDefinition(
                    id="second",
                    plugin=PluginSpec("quantmine.pipeline_stages:second"),
                    upstream=("first",),
                ),
            ),
            "cycle",
        ),
    ],
)
def test_definition_rejects_invalid_dependencies(
    stages: tuple[PipelineStageDefinition, ...],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        MarketPipelineDefinition(
            id="invalid_pipeline",
            dag_id="quantmine_invalid_pipeline",
            display_name="Invalid",
            schedule="0 0 * * *",
            stages=stages,
        )


def test_definition_rejects_duplicate_or_unsafe_connection_aliases() -> None:
    with pytest.raises(ValueError, match="duplicate connection"):
        MarketPipelineDefinition(
            id="invalid_connections",
            dag_id="quantmine_invalid_connections",
            display_name="Invalid",
            schedule="0 0 * * *",
            connection_refs=("cn_lake", "cn_lake"),
            stages=(
                PipelineStageDefinition(
                    id="stage",
                    plugin=PluginSpec("quantmine.pipeline_stages:stage"),
                ),
            ),
        )

    with pytest.raises(ValueError, match="connection ref"):
        MarketPipelineDefinition(
            id="invalid_connection_name",
            dag_id="quantmine_invalid_connection_name",
            display_name="Invalid",
            schedule="0 0 * * *",
            connection_refs=("CN-LAKE",),
            stages=(
                PipelineStageDefinition(
                    id="stage",
                    plugin=PluginSpec("quantmine.pipeline_stages:stage"),
                ),
            ),
        )

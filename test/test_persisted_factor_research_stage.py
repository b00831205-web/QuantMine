"""Tests for the configured DAG stage that executes persisted research."""

from __future__ import annotations

from pathlib import Path

import quantmine.plugins.research_stages as research_stages
import pytest
from quantmine.market_pipeline_config import (
    MarketPipelineDefinition,
    PipelineStageDefinition,
)
from quantmine.pipeline_stages import PipelineStageRequest
from quantmine.plugins.context import SourceContext
from quantmine.plugins.contracts import DataBinding, PluginSpec
from quantmine.research import FactorResearchResult
from quantmine.research_config import ResearchRunConfig


class _Connections:
    def __init__(self) -> None:
        self.requested_refs: list[str] = []
        self.engine = object()

    def sqlalchemy_engine(self, connection_ref: str) -> object:
        self.requested_refs.append(connection_ref)
        return self.engine


def _request(tmp_path: Path, *, batch_id: str = "scheduled__2026-09-14") -> PipelineStageRequest:
    stage = PipelineStageDefinition(
        id="factor_research",
        plugin=PluginSpec("fixture:create_stage"),
    )
    pipeline = MarketPipelineDefinition(
        id="cn_research",
        dag_id="quantmine_cn_research",
        display_name="CN research",
        schedule="0 18 * * 1-5",
        stages=(stage,),
    )
    return PipelineStageRequest(
        pipeline=pipeline,
        stage=stage,
        context=SourceContext(
            connections=_Connections(),
            run_id=0,
            artifact_dir=tmp_path / "pipeline-artifacts",
        ),
        as_of_date="2026-09-14",
        batch_id=batch_id,
    )


def _config() -> ResearchRunConfig:
    return ResearchRunConfig.from_bundle_id(
        "cn_a_share_v1",
        DataBinding(
            connection_ref="cn_market",
            dataset="cn_a_share_daily_bars",
            version="20260910",
            start="2026-01-01",
            end="2026-09-14",
        ),
    )


def test_persisted_factor_research_stage_creates_a_batch_run_and_executes_it(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config = _config()
    request = _request(tmp_path)
    observed: dict[str, object] = {}

    monkeypatch.setattr(
        research_stages,
        "get_or_create_research_run_for_batch",
        lambda engine, persisted_config, *, batch_id: (
            observed.update(
                engine=engine,
                config=persisted_config,
                batch_id=batch_id,
            )
            or 812
        ),
    )
    monkeypatch.setattr(
        research_stages,
        "execute_persisted_research",
        lambda store, run_id, *, artifact_root, allowed_module_prefixes: (
            observed.update(
                store=store,
                run_id=run_id,
                artifact_root=artifact_root,
                allowed_module_prefixes=allowed_module_prefixes,
            )
            or FactorResearchResult(
                market_data=None,
                requested_signals=("CNMomentum20D", "CNReversal5D"),
                factors={"CNMomentum20D": object()},
                pending={"CNReversal5D": "insufficient history"},
            )
        ),
    )

    stage = research_stages.create_persisted_factor_research_stage(
        research_run_connection_ref="research_db",
        config=config.to_snapshot(),
    )
    result = stage.run(request)

    assert request.context.connections.requested_refs == ["research_db"]
    assert observed["engine"] is request.context.connections.engine
    assert observed["config"] == config
    assert observed["batch_id"] == "scheduled__2026-09-14"
    assert observed["run_id"] == 812
    assert observed["artifact_root"] == request.context.artifact_dir
    assert observed["allowed_module_prefixes"] == ("quantmine",)
    assert result.metadata == {
        "research_run_id": 812,
        "requested_signal_count": 2,
        "factor_count": 1,
        "pending_count": 1,
        "factor_artifact_dir": str(
            request.context.artifact_dir / "factor_research" / "812"
        ),
    }


def test_persisted_factor_research_stage_rejects_an_invalid_config_snapshot() -> None:
    with pytest.raises(ValueError, match="Unsupported"):
        research_stages.create_persisted_factor_research_stage(
            research_run_connection_ref="research_db",
            config={"schema_version": 999},
        )

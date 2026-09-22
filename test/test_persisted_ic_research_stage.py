"""Tests for the configured DAG stage that executes persisted IC research."""

from __future__ import annotations

from pathlib import Path

import pytest

from quantmine.market_pipeline_config import (
    MarketPipelineDefinition,
    PipelineStageDefinition,
)
from quantmine.pipeline_stages import PipelineStageRequest
from quantmine.plugins import ic_stages
from quantmine.plugins.context import SourceContext
from quantmine.plugins.contracts import PluginSpec


class _Connections:
    def __init__(self) -> None:
        self.requested_refs: list[str] = []
        self.engine = object()

    def sqlalchemy_engine(self, connection_ref: str) -> object:
        self.requested_refs.append(connection_ref)
        return self.engine


def _request(
    tmp_path: Path,
    *,
    batch_id: str = "scheduled__2026-09-14",
) -> PipelineStageRequest:
    factor_stage = PipelineStageDefinition(
        id="factor_research",
        plugin=PluginSpec("fixture:create_factor_stage"),
    )
    ic_stage = PipelineStageDefinition(
        id="ic_research",
        plugin=PluginSpec("fixture:create_ic_stage"),
        upstream=("factor_research",),
    )
    pipeline = MarketPipelineDefinition(
        id="cn_research",
        dag_id="quantmine_cn_research",
        display_name="CN research",
        schedule="0 18 * * 1-5",
        stages=(factor_stage, ic_stage),
    )
    return PipelineStageRequest(
        pipeline=pipeline,
        stage=ic_stage,
        context=SourceContext(
            connections=_Connections(),
            run_id=0,
            artifact_dir=tmp_path / "pipeline-artifacts",
        ),
        as_of_date="2026-09-14",
        batch_id=batch_id,
        allowed_module_prefixes=("quantmine", "vendor_ic"),
    )


def test_persisted_ic_research_stage_resumes_batch_run_and_executes_it(
    monkeypatch,
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    observed: dict[str, object] = {}

    monkeypatch.setattr(
        ic_stages,
        "find_run_id_by_airflow_batch",
        lambda engine, batch_id: (
            observed.update(lookup_engine=engine, batch_id=batch_id) or 812
        ),
    )
    monkeypatch.setattr(
        ic_stages.execution,
        "execute_persisted_ic_research",
        lambda store, run_id, *, artifact_root, allowed_module_prefixes: (
            observed.update(
                store=store,
                run_id=run_id,
                artifact_root=artifact_root,
                allowed_module_prefixes=allowed_module_prefixes,
            )
            or (
                {"raw": object(), "orthogonalized": object()},
                {"newey_raw": object()},
            )
        ),
        raising=False,
    )

    stage = ic_stages.create_persisted_ic_research_stage(
        research_run_connection_ref="research_db",
    )
    result = stage.run(request)

    assert request.context.connections.requested_refs == ["research_db"]
    assert observed["lookup_engine"] is request.context.connections.engine
    assert observed["batch_id"] == "scheduled__2026-09-14"
    assert observed["run_id"] == 812
    assert observed["artifact_root"] == request.context.artifact_dir
    assert observed["allowed_module_prefixes"] == (
        "quantmine",
        "vendor_ic",
    )
    assert result.metadata == {
        "research_run_id": 812,
        "variant_count": 2,
        "test_count": 1,
        "ic_artifact_dir": str(
            request.context.artifact_dir / "ic_research" / "812"
        ),
    }


@pytest.mark.parametrize(
    "connection_ref",
    ["", " research_db", "research_db "],
)
def test_persisted_ic_research_stage_rejects_invalid_connection_ref(
    connection_ref: str,
) -> None:
    with pytest.raises(ValueError, match="research_run_connection_ref"):
        ic_stages.create_persisted_ic_research_stage(
            research_run_connection_ref=connection_ref,
        )

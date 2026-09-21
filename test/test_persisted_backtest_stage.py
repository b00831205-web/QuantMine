"""Tests for the configured DAG stage that executes persisted backtests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from quantmine.market_pipeline_config import (
    MarketPipelineDefinition,
    PipelineStageDefinition,
)
from quantmine.pipeline_stages import PipelineStageRequest
from quantmine.plugins import backtest_stage
from quantmine.plugins.context import SourceContext
from quantmine.plugins.contracts import PluginSpec


class _Connections:
    def __init__(self) -> None:
        self.requested_refs: list[str] = []
        self.engine = object()

    def sqlalchemy_engine(self, connection_ref: str) -> object:
        self.requested_refs.append(connection_ref)
        return self.engine


def _request(tmp_path: Path) -> PipelineStageRequest:
    stage = PipelineStageDefinition(
        id="backtest",
        plugin=PluginSpec("fixture:create_backtest_stage"),
        upstream=("ic_research",),
    )
    pipeline = MarketPipelineDefinition(
        id="cn_research",
        dag_id="quantmine_cn_research",
        display_name="CN research",
        schedule="0 18 * * 1-5",
        stages=(
            PipelineStageDefinition(
                id="ic_research",
                plugin=PluginSpec("fixture:create_ic_stage"),
            ),
            stage,
        ),
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
        batch_id="scheduled__2026-09-14",
        allowed_module_prefixes=("quantmine", "vendor_backtest"),
    )


def test_persisted_backtest_stage_resumes_run_and_reports_manifest(
    monkeypatch,
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    observed: dict[str, object] = {}
    run_manifest = (
        request.context.artifact_dir
        / "position_backtests"
        / "812"
        / "run_manifest.json"
    )
    run_manifest.parent.mkdir(parents=True)
    run_manifest.touch()

    monkeypatch.setattr(
        backtest_stage,
        "find_run_id_by_airflow_batch",
        lambda engine, batch_id: (
            observed.update(lookup_engine=engine, batch_id=batch_id) or 812
        ),
    )
    monkeypatch.setattr(
        backtest_stage.execution,
        "execute_persisted_backtest",
        lambda store, run_id, *, artifact_root, allowed_module_prefixes: (
            observed.update(
                store=store,
                run_id=run_id,
                artifact_root=artifact_root,
                allowed_module_prefixes=allowed_module_prefixes,
            )
            or SimpleNamespace(job_results={"raw": {}, "orthogonalized": {}})
        ),
    )

    stage = backtest_stage.create_persisted_backtest_stage(
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
        "vendor_backtest",
    )
    assert result.metadata == {
        "research_run_id": 812,
        "backtest_job_count": 2,
        "position_backtest_artifact_dir": str(run_manifest.parent),
        "position_backtest_run_manifest": str(run_manifest),
    }


@pytest.mark.parametrize(
    "connection_ref",
    ["", " research_db", "research_db "],
)
def test_persisted_backtest_stage_rejects_invalid_connection_ref(
    connection_ref: str,
) -> None:
    with pytest.raises(ValueError, match="research_run_connection_ref"):
        backtest_stage.create_persisted_backtest_stage(
            research_run_connection_ref=connection_ref,
        )

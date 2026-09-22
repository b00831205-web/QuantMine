"""Runtime assembly for one configured market-pipeline stage."""

from __future__ import annotations

from pathlib import Path

import pytest

from quantmine.market_pipeline_config import (
    MarketPipelineDefinition,
    PipelineStageDefinition,
    PipelineStageKind,
)
from quantmine.pipeline_runtime import (
    evaluate_configured_session_gate,
    run_configured_pipeline_stage,
)
import quantmine.pipeline_runtime as pipeline_runtime
from quantmine.pipeline_stages import PipelineStageResult
from quantmine.plugins.contracts import PluginSpec


class _Gate:
    def allows(self, request) -> bool:
        return request.context.artifact_dir.is_dir()


class _Task:
    def run(self, request) -> PipelineStageResult:
        return PipelineStageResult(
            metadata={
                "pipeline": request.pipeline.id,
                "run_id": request.context.run_id,
                "artifact_dir": str(request.context.artifact_dir),
            },
        )


def create_gate() -> _Gate:
    return _Gate()


def create_task() -> _Task:
    return _Task()


def _pipeline() -> MarketPipelineDefinition:
    return MarketPipelineDefinition(
        id="runtime_fixture",
        dag_id="quantmine_runtime_fixture",
        display_name="Runtime fixture",
        schedule="0 0 * * *",
        stages=(
            PipelineStageDefinition(
                id="session_gate",
                kind=PipelineStageKind.SESSION_GATE,
                plugin=PluginSpec("test_pipeline_runtime:create_gate"),
            ),
            PipelineStageDefinition(
                id="task",
                plugin=PluginSpec("test_pipeline_runtime:create_task"),
                upstream=("session_gate",),
            ),
        ),
    )


def test_runtime_executes_a_stage_from_a_serialized_definition(
    tmp_path: Path,
) -> None:
    result = run_configured_pipeline_stage(
        pipeline_snapshot=_pipeline().to_snapshot(),
        stage_id="task",
        as_of_date="2024-01-02",
        batch_id="scheduled__2024-01-02",
        artifact_root=tmp_path,
        allowed_module_prefixes=("quantmine", "test_pipeline_runtime"),
    )

    assert result["pipeline"] == "runtime_fixture"
    assert result["run_id"] == 0
    assert Path(result["artifact_dir"]).is_dir()


def test_runtime_evaluates_a_session_gate_from_a_serialized_definition(
    tmp_path: Path,
) -> None:
    assert evaluate_configured_session_gate(
        pipeline_snapshot=_pipeline().to_snapshot(),
        stage_id="session_gate",
        as_of_date="2024-01-02",
        batch_id="scheduled__2024-01-02",
        artifact_root=tmp_path,
        allowed_module_prefixes=("quantmine", "test_pipeline_runtime"),
    ) is True


def test_runtime_rejects_a_non_object_pipeline_snapshot(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="pipeline snapshot"):
        run_configured_pipeline_stage(
            pipeline_snapshot=[],
            stage_id="task",
            as_of_date="2024-01-02",
            batch_id="manual",
            artifact_root=tmp_path,
        )


def test_runtime_loads_environment_before_resolving_connections(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls: list[Path | str | None] = []
    monkeypatch.setattr(
        pipeline_runtime,
        "load_environment_file",
        lambda path: calls.append(path),
    )
    env_file = tmp_path / ".env"

    run_configured_pipeline_stage(
        pipeline_snapshot=_pipeline().to_snapshot(),
        stage_id="task",
        as_of_date="2024-01-02",
        batch_id="manual",
        artifact_root=tmp_path,
        environment_file=env_file,
        allowed_module_prefixes=("quantmine", "test_pipeline_runtime"),
    )

    assert calls == [env_file]

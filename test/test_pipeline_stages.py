"""Runtime contracts for generic market-pipeline stage plugins."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from quantmine.market_pipeline_config import (
    MarketPipelineDefinition,
    PipelineStageDefinition,
    PipelineStageKind,
)
from quantmine.pipeline_stages import (
    PipelineStageResult,
    evaluate_session_gate,
    run_pipeline_stage,
)
from quantmine.plugins.context import SourceContext
from quantmine.plugins.contracts import PluginSpec
from quantmine.storage.connections import ConnectionRegistry


class _PassingGate:
    def allows(self, request) -> bool:
        assert request.as_of_date == pd.Timestamp("2024-01-02")
        assert request.batch_id == "scheduled__2024-01-02"
        return True


class _RecordingTask:
    def run(self, request) -> PipelineStageResult:
        return PipelineStageResult(
            metadata={
                "pipeline": request.pipeline.id,
                "stage": request.stage.id,
                "date": request.as_of_date.date().isoformat(),
            },
        )


class _InvalidTask:
    def run(self, request) -> object:
        del request
        return object()


def create_passing_gate() -> _PassingGate:
    return _PassingGate()


def create_recording_task() -> _RecordingTask:
    return _RecordingTask()


def create_invalid_task() -> _InvalidTask:
    return _InvalidTask()


def _pipeline() -> MarketPipelineDefinition:
    return MarketPipelineDefinition(
        id="cn_research",
        dag_id="quantmine_cn_research",
        display_name="CN research",
        schedule="0 18 * * 1-5",
        stages=(
            PipelineStageDefinition(
                id="session_gate",
                kind=PipelineStageKind.SESSION_GATE,
                plugin=PluginSpec("test_pipeline_stages:create_passing_gate"),
            ),
            PipelineStageDefinition(
                id="research",
                plugin=PluginSpec("test_pipeline_stages:create_recording_task"),
                upstream=("session_gate",),
            ),
        ),
    )


def _context(tmp_path: Path) -> SourceContext:
    return SourceContext(
        connections=ConnectionRegistry({}),
        run_id=0,
        artifact_dir=tmp_path / "artifacts",
    )


def test_generic_stage_runner_resolves_and_executes_a_task_plugin(
    tmp_path: Path,
) -> None:
    result = run_pipeline_stage(
        _pipeline(),
        stage_id="research",
        context=_context(tmp_path),
        as_of_date="2024-01-02",
        batch_id="scheduled__2024-01-02",
        allowed_module_prefixes=("quantmine", "test_pipeline_stages"),
    )

    assert result.metadata == {
        "pipeline": "cn_research",
        "stage": "research",
        "date": "2024-01-02",
    }


def test_generic_session_gate_resolves_and_evaluates_its_plugin(
    tmp_path: Path,
) -> None:
    assert evaluate_session_gate(
        _pipeline(),
        stage_id="session_gate",
        context=_context(tmp_path),
        as_of_date="2024-01-02",
        batch_id="scheduled__2024-01-02",
        allowed_module_prefixes=("quantmine", "test_pipeline_stages"),
    ) is True


def test_stage_runner_rejects_a_plugin_with_an_invalid_result(
    tmp_path: Path,
) -> None:
    pipeline = MarketPipelineDefinition(
        id="invalid_result",
        dag_id="quantmine_invalid_result",
        display_name="Invalid result",
        schedule="0 0 * * *",
        stages=(
            PipelineStageDefinition(
                id="task",
                plugin=PluginSpec("test_pipeline_stages:create_invalid_task"),
            ),
        ),
    )

    with pytest.raises(TypeError, match="PipelineStageResult"):
        run_pipeline_stage(
            pipeline,
            stage_id="task",
            context=_context(tmp_path),
            as_of_date="2024-01-02",
            batch_id="manual",
            allowed_module_prefixes=("quantmine", "test_pipeline_stages"),
        )


def test_stage_result_rejects_non_json_metadata() -> None:
    with pytest.raises(TypeError, match="JSON-serializable"):
        PipelineStageResult(metadata={"invalid": object()})


def test_unknown_stage_error_names_the_requested_stage(tmp_path: Path) -> None:
    with pytest.raises(KeyError, match="missing_stage"):
        run_pipeline_stage(
            _pipeline(),
            stage_id="missing_stage",
            context=_context(tmp_path),
            as_of_date="2024-01-02",
            batch_id="manual",
            allowed_module_prefixes=("quantmine", "test_pipeline_stages"),
        )

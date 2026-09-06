"""Airflow DAG construction from persistent market-pipeline definitions."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import quantmine.airflow_dag_factory as dag_factory
from quantmine.airflow_dag_factory import build_market_pipeline_dag
from quantmine.market_pipeline_config import (
    MarketPipelineDefinition,
    PipelineStageDefinition,
    PipelineStageKind,
)
from quantmine.pipeline_runtime import (
    evaluate_configured_session_gate,
    run_configured_pipeline_stage,
)
from quantmine.plugins.contracts import PluginSpec


class FakeDag:
    active: "FakeDag | None" = None

    def __init__(self, dag_id: str, **kwargs) -> None:
        self.dag_id = dag_id
        self.kwargs = kwargs
        self.tasks: list[FakeOperator] = []

    def __enter__(self) -> "FakeDag":
        type(self).active = self
        return self

    def __exit__(self, *args: object) -> None:
        type(self).active = None


class FakeOperator:
    def __init__(self, *, task_id: str, python_callable, op_kwargs) -> None:
        self.task_id = task_id
        self.python_callable = python_callable
        self.op_kwargs = op_kwargs
        self.downstream: list[FakeOperator] = []
        assert FakeDag.active is not None
        FakeDag.active.tasks.append(self)

    def __rshift__(self, other: "FakeOperator") -> "FakeOperator":
        self.downstream.append(other)
        return other


class FakePythonOperator(FakeOperator):
    pass


class FakeShortCircuitOperator(FakeOperator):
    pass


def _definition() -> MarketPipelineDefinition:
    return MarketPipelineDefinition(
        id="generic_equity",
        dag_id="quantmine_generic_equity",
        display_name="Generic equity research",
        schedule="0 18 * * 1-5",
        stages=(
            PipelineStageDefinition(
                id="session_gate",
                kind=PipelineStageKind.SESSION_GATE,
                plugin=PluginSpec("local_plugins:create_session_gate"),
            ),
            PipelineStageDefinition(
                id="production",
                plugin=PluginSpec("local_plugins:create_production"),
                upstream=("session_gate",),
            ),
            PipelineStageDefinition(
                id="research",
                plugin=PluginSpec("local_plugins:create_research"),
                upstream=("production",),
            ),
            PipelineStageDefinition(
                id="ic",
                plugin=PluginSpec("local_plugins:create_ic"),
                upstream=("research",),
            ),
            PipelineStageDefinition(
                id="backtest",
                plugin=PluginSpec("local_plugins:create_backtest"),
                upstream=("research",),
            ),
            PipelineStageDefinition(
                id="publish",
                plugin=PluginSpec("local_plugins:create_publish"),
                upstream=("ic", "backtest"),
            ),
        ),
    )


def test_factory_builds_gate_tasks_and_fan_out_fan_in_dependencies(
    tmp_path: Path,
) -> None:
    dag = build_market_pipeline_dag(
        _definition(),
        start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        artifact_root=tmp_path,
        environment_file=tmp_path / ".env",
        allowed_module_prefixes=("quantmine", "local_plugins"),
        dag_class=FakeDag,
        python_operator_class=FakePythonOperator,
        short_circuit_operator_class=FakeShortCircuitOperator,
    )

    tasks = {task.task_id: task for task in dag.tasks}
    assert dag.dag_id == "quantmine_generic_equity"
    assert dag.kwargs["schedule"] == "0 18 * * 1-5"
    assert dag.kwargs["catchup"] is False
    assert dag.kwargs["max_active_runs"] == 1

    assert isinstance(tasks["session_gate"], FakeShortCircuitOperator)
    assert tasks["session_gate"].python_callable is (
        evaluate_configured_session_gate
    )
    assert tasks["research"].python_callable is run_configured_pipeline_stage
    assert tasks["research"].op_kwargs["as_of_date"] == (
        "{{ dag_run.run_after | ds }}"
    )
    assert tasks["research"].op_kwargs["batch_id"] == "{{ run_id }}"
    assert tasks["research"].op_kwargs["environment_file"] == str(
        tmp_path / ".env"
    )

    assert [task.task_id for task in tasks["session_gate"].downstream] == [
        "production"
    ]
    assert [task.task_id for task in tasks["research"].downstream] == [
        "ic",
        "backtest",
    ]
    assert [task.task_id for task in tasks["ic"].downstream] == ["publish"]
    assert [task.task_id for task in tasks["backtest"].downstream] == [
        "publish"
    ]


def test_factory_uses_lazy_airflow_types_when_classes_are_not_injected(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        dag_factory,
        "_airflow_types",
        lambda: (
            FakeDag,
            FakePythonOperator,
            FakeShortCircuitOperator,
        ),
    )

    dag = build_market_pipeline_dag(
        _definition(),
        start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        artifact_root=tmp_path,
    )

    tasks = {task.task_id: task for task in dag.tasks}
    assert isinstance(tasks["session_gate"], FakeShortCircuitOperator)
    assert isinstance(tasks["production"], FakePythonOperator)

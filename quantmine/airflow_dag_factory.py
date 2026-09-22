"""Build Airflow DAGs from persistent market-pipeline definitions"""

from __future__ import annotations
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from .market_pipeline_config import(
    MarketPipelineDefinition,
    PipelineStageKind,
)

from .pipeline_runtime import (
    evaluate_configured_session_gate,
    run_configured_pipeline_stage,
)

def build_market_pipeline_dag(
        definition: MarketPipelineDefinition,
        *,
        start_date: datetime,
        artifact_root: Path | str,
        allowed_module_prefixes: Iterable[str] | None = ("quantmine",),
        default_args : Mapping[str, Any] | None = None,
        tags: Sequence[str] = (),
        dag_class = None,
        python_operator_class = None,
        short_circuit_operator_class = None,
        environment_file: Path | str | None = None
):
    """Construct an Airflow DAG from one persistent pipeline definition."""

    if (
        dag_class is None or python_operator_class is None or short_circuit_operator_class is None
    ):
        (
            airflow_dag_class, airflow_python_operator, airflow_short_circuit_operator,
        ) = _airflow_types()

        dag_class = dag_class or airflow_dag_class
        python_operator_class = (
            python_operator_class or airflow_python_operator
        )

        short_circuit_operator_class = (
            short_circuit_operator_class or airflow_short_circuit_operator
        )

    pipeline_snapshot = definition.to_snapshot()
    module_prefixes = (
        None if allowed_module_prefixes is None else tuple(allowed_module_prefixes)
    )

    with dag_class(
        definition.dag_id,
        description = definition.display_name,
        schedule = definition.schedule,
        start_date = start_date,
        catchup = False,
        max_active_runs = 1,
        default_args = dict(default_args or {}),
        tags = [*tags, definition.id],
        
    ) as dag:
        tasks = {}
        for stage in definition.stages:
            if stage.kind is PipelineStageKind.SESSION_GATE:
                operator_class = short_circuit_operator_class
                python_callable = evaluate_configured_session_gate
            else:
                operator_class = python_operator_class
                python_callable = run_configured_pipeline_stage

            tasks[stage.id] = operator_class(
                task_id = stage.id,
                python_callable = python_callable,
                op_kwargs = {
                    "pipeline_snapshot": pipeline_snapshot,
                    "stage_id": stage.id,
                    "as_of_date": "{{ dag_run.run_after | ds }}",
                    "batch_id": "{{ run_id }}",
                    "artifact_root": str(artifact_root),
                    "allowed_module_prefixes": module_prefixes,
                    "environment_file": (None if environment_file is None else str(environment_file))
                },
            )
        for stage in definition.stages:
            for upstream_id in stage.upstream:
                tasks[upstream_id] >> tasks[stage.id]

    return dag

def _airflow_types():
    """Import Airflow only when a real DAG is being constructed"""

    try:
        from airflow.sdk import DAG
        from airflow.providers.standard.operators.python import (
            PythonOperator,
            ShortCircuitOperator
        )

    except ImportError as error:
        raise RuntimeError(
            "Airflow DAG construction requires the pipeline dependency group"
        ) from error

    return DAG, PythonOperator, ShortCircuitOperator
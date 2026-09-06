"""Discovery test for the single configuration-driven Airflow DAG file."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path
from types import ModuleType


PROJECT_ROOT = Path(__file__).parents[1]


class FakeDag:
    active: "FakeDag | None" = None

    def __init__(self, dag_id: str, **kwargs) -> None:
        self.dag_id = dag_id
        self.kwargs = kwargs
        self.tasks = []

    @property
    def task_ids(self) -> list[str]:
        return [task.task_id for task in self.tasks]

    def __enter__(self):
        type(self).active = self
        return self

    def __exit__(self, *args: object) -> None:
        type(self).active = None


class FakeOperator:
    def __init__(self, *, task_id: str, python_callable, op_kwargs) -> None:
        self.task_id = task_id
        self.python_callable = python_callable
        self.op_kwargs = op_kwargs
        self.downstream = []
        assert FakeDag.active is not None
        FakeDag.active.tasks.append(self)

    def __rshift__(self, other):
        self.downstream.append(other)
        return other


def _install_fake_airflow(monkeypatch) -> None:
    module_names = (
        "airflow",
        "airflow.sdk",
        "airflow.providers",
        "airflow.providers.standard",
        "airflow.providers.standard.operators",
        "airflow.providers.standard.operators.python",
    )
    modules = {name: ModuleType(name) for name in module_names}
    modules["airflow.sdk"].DAG = FakeDag
    python_module = modules[
        "airflow.providers.standard.operators.python"
    ]
    python_module.PythonOperator = FakeOperator
    python_module.ShortCircuitOperator = FakeOperator
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)


def test_dag_file_discovers_configured_a_share_pipeline(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _install_fake_airflow(monkeypatch)
    monkeypatch.setenv("QUANT_PROJECT_ROOT", str(PROJECT_ROOT))
    monkeypatch.setenv(
        "QUANT_MARKET_PIPELINE_CONFIG_PATH",
        "config.example.yaml",
    )
    monkeypatch.setenv(
        "QUANT_PIPELINE_ARTIFACT_ROOT",
        str(tmp_path / "artifacts"),
    )
    monkeypatch.setenv(
        "QUANTMINE_PLUGIN_ALLOWED_PREFIXES",
        "quantmine",
    )

    namespace = runpy.run_path(
        str(PROJECT_ROOT / "pipelines" / "DAG_market_pipeline.py")
    )

    dag = namespace["dag_cn_a_share_daily"]
    assert dag.dag_id == "quantmine_cn_a_share_daily"
    assert dag.task_ids == ["session_gate", "daily_production"]
    tasks = {task.task_id: task for task in dag.tasks}
    assert tasks["session_gate"].downstream == [
        tasks["daily_production"]
    ]
    assert tasks["daily_production"].op_kwargs[
        "environment_file"
    ] == str(PROJECT_ROOT / ".env")

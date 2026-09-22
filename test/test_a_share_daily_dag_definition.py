"""Static contract checks for the A-share Airflow DAG definition.

The normal test environment deliberately does not install Airflow provider
packages, so this test verifies the portable DAG source without importing it.
"""

from __future__ import annotations

import ast
from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DAG_PATH = PROJECT_ROOT / "pipelines" / "DAG_a_share_daily.py"


def test_a_share_daily_dag_is_a_single_serial_weekday_production_task() -> None:
    source = DAG_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    dag_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", None) == "DAG"
    ]
    assert len(dag_calls) == 1
    dag_call = dag_calls[0]
    assert isinstance(dag_call.args[0], ast.Constant)
    assert dag_call.args[0].value == "quantmine_a_share_daily"

    dag_keywords = {
        keyword.arg: keyword.value
        for keyword in dag_call.keywords
        if keyword.arg is not None
    }
    assert isinstance(dag_keywords["schedule"], ast.Constant)
    assert dag_keywords["schedule"].value == "0 18 * * 1-5"
    assert isinstance(dag_keywords["catchup"], ast.Constant)
    assert dag_keywords["catchup"].value is False
    assert isinstance(dag_keywords["max_active_runs"], ast.Constant)
    assert dag_keywords["max_active_runs"].value == 1

    assert "a_share_daily_production" in source
    assert "pipelines/task_a_share_daily_pipeline.py" in source
    assert "QUANT_A_SHARE_DAILY_CONFIG_PATH" in source
    assert re.search(r"\{\{\s*dag_run\.run_after\s*\|\s*ds\s*\}\}", source)
    assert re.search(r"\{\{\s*run_id\s*\}\}", source)

    assert any(
        isinstance(node, ast.With)
        and any(
            isinstance(item.context_expr, ast.Call)
            and getattr(item.context_expr.func, "id", None) == "DAG"
            for item in node.items
        )
        for node in ast.walk(tree)
    )

"""Static checks for the market-session short-circuit tasks in both DAGs."""

from __future__ import annotations

from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_a_share_dag_short_circuits_production_on_non_sessions() -> None:
    source = (PROJECT_ROOT / "pipelines" / "DAG_a_share_daily.py").read_text(
        encoding="utf-8",
    )

    assert "ShortCircuitOperator" in source
    assert re.search(
        r'task_id\s*=\s*["\']a_share_market_session_gate["\']',
        source,
    )
    assert "is_a_share_trading_session" in source
    assert "a_share_session_gate_task >> a_share_daily_production" in source


def test_us_dag_short_circuits_the_existing_pipeline_on_non_sessions() -> None:
    source = (PROJECT_ROOT / "pipelines" / "DAG_pipeline.py").read_text(
        encoding="utf-8",
    )

    assert "ShortCircuitOperator" in source
    assert re.search(
        r'task_id\s*=\s*["\']us_market_session_gate["\']',
        source,
    )
    assert "is_xnys_trading_session" in source
    assert "us_market_session_gate >> t0" in source

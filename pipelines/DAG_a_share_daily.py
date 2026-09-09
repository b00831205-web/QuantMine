"""Airflow DAG for A-share daily raw/status/eligibility production"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

from airflow.providers.standard.operators.bash import BashOperator
from airflow.providers.standard.operators.python import ShortCircuitOperator
from airflow.sdk import DAG

PROJECT_ROOT = os.environ.get(
    "QUANT_PROJECT_ROOT",
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)
sys.path.insert(0, PROJECT_ROOT)

from pipelines.task_a_share_daily_pipeline import (
    load_a_share_daily_pipeline_config,
    load_project_environment,
    required_connection_refs,
)

from quantmine.plugins.context import SourceContext
from quantmine.storage.connections import ConnectionRegistry
from quantmine.workflows.a_share_daily_pipeline import (
    is_a_share_trading_session,
)

PYTHON_BIN_EXPR = '"${QUANT_PYTHON_BIN:-.venv/bin/python}"'
A_SHARE_CONFIG_EXPR = '"${QUANT_A_SHARE_DAILY_CONFIG_PATH:-config.yaml}"'

def a_share_market_session_gate(as_of_date: str) -> bool:
    """Return False on a CN non-trading day, causing downstream skip."""

    load_project_environment()
    config_path = os.environ.get(
        "QUANT_A_SHARE_DAILY_CONFIG_PATH",
        "config.yaml"
    )
    config = load_a_share_daily_pipeline_config(PROJECT_ROOT / config_path)
    context = SourceContext(
        conncetions = ConnectionRegistry.from_environment(
            required_connection_refs(config),
        ),
        run_id = 0,
        artifact_dir= PROJECT_ROOT / "data" / "artifacts" / "a_share_daily"
    )
    allowed = is_a_share_trading_session(
        context,
        config = config,
        as_of_date = as_of_date,
    )
    print(f"A-share session gate: date={as_of_date}, allowed={allowed}")
    return allowed

def a_share_task_command() -> str:
    return (
        f'cd "{PROJECT_ROOT}" && '
        '{ set -a; [ -f .env ] && . ./.env; set +a; } && '
        'export https_proxy="${https_proxy:-$http_proxy}" && '
        'export HTTP_PROXY="${HTTP_PROXY:-$http_proxy}" && '
        'export HTTPS_PROXY="${HTTPS_PROXY:-$https_proxy}" && '
        f'{PYTHON_BIN_EXPR} -u pipelines/task_a_share_daily_pipeline.py '
        '--date {{ dag_run.run_after | ds }} '
        '--batch {{ run_id }} '
        f'--config {A_SHARE_CONFIG_EXPR}'
    )

with DAG(
    "quantmine_a_share_daily",
    default_args={
        "retries": 1,
        "retry_delay": timedelta(minutes=10)
    },
    description = "Daily A-share raw snapshot, market status, and eligibility",
    schedule = "0 18 * * 1-5",
    start_date = datetime(2026, 1, 1, tzinfo=timezone.utc),
    catchup = False,
    max_active_runs = 1,
    tags = ["quant_factor_mining", "a_share", "production"],
) as dag:
    a_share_session_gate_task = ShortCircuitOperator(
        task_id = "a_share_market_session_gate",
        python_callable = a_share_market_session_gate,
        op_kwargs = {"as_of_date": "{{ dag_run.run_after | ds }}"},
    )
    a_share_daily_production = BashOperator(
        task_id = "a_share_daily_production",
        bash_command = a_share_task_command(),
    )

a_share_session_gate_task >> a_share_daily_production
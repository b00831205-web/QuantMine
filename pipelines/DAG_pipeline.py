"""Airflow DAG for the daily data-download / clean / factor-calculation loop.

Configuration comes from environment variables so the DAG file itself is
portable across machines:

    QUANT_PROJECT_ROOT  Absolute path of this project. Defaults to the parent
                        of the directory containing this file (repo root).
    QUANT_PYTHON_BIN    Python interpreter used to run the task scripts.
                        Defaults to ``python``. On a WSL-hosted Airflow that
                        drives a Windows venv, point it at
                        ``.venv-win/Scripts/python.exe`` (WSL interop launches
                        Windows executables directly, no PowerShell wrapper
                        needed).
"""
import os
from datetime import datetime, timedelta, timezone
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

PROJECT_ROOT = os.environ.get("QUANT_PROJECT_ROOT",
                              os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PYTHON_BIN = os.environ.get("QUANT_PYTHON_BIN", "python")
CONFIG_PATH = os.environ.get("QUANT_CONFIG_PATH", "config.example.yaml")


def task_command(script: str, *, uses_config: bool = False) -> str:
    """Build the bash command that runs one pipeline script.

    Args:
        script: Script filename inside the ``pipelines/`` directory.

    Returns:
        A bash command string with the Airflow ``ds``/``run_id`` templates.

    Notes:
        The command runs from the repo root so that relative data paths
        (``tmp/``, ``data/``) resolve correctly.
    """
    command = (
        f'cd "{PROJECT_ROOT}" && "{PYTHON_BIN}" pipelines/{script} '
        '--date {{ ds }} --batch {{ run_id }}'
    )
    if uses_config:
        command += f' --config "{CONFIG_PATH}"'
    return command


with DAG("quant_factor_mining",
        default_args={
            "retries": 1,
            "retry_delay": timedelta(minutes=5)
        },
        description="quant_factor_mining pipeline version 0.1, using S&P 500",
        schedule=timedelta(days=1),
        start_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
        catchup=False,
        tags=['quant_factor_mining'],
        ) as dag:
    t1 = BashOperator(
        task_id="data_downloading",
        bash_command=task_command("task_1.py"),
    )
    t2 = BashOperator(
        task_id="data_cleaning",
        bash_command=task_command("task_2.py"),
    )
    t3 = BashOperator(
        task_id="factor_calculation",
        bash_command=task_command("task_3.py"),
    )
    t4 = BashOperator(
        task_id="ic_calculation",
        bash_command=task_command("task_ic_calculate.py", uses_config=True),
    )
    task_save_market_bars = BashOperator(
        task_id="save_market_bars",
        bash_command=task_command("task_save_market_bars.py"),
    )
    t5 = BashOperator(
        task_id="backtest",
        bash_command=task_command("task_backtest.py", uses_config=True),
    )

t1 >> t2 >> t3 >> t4
t4 >> [task_save_market_bars, t5]

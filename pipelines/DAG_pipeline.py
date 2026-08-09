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
    # 连库任务需要 QUANTMINE_DATABASE_URL（在项目 .env 里）。Airflow 任务子进程不会
    # 自动加载 .env，故运行脚本前先 source 一次（set -a 让其中变量导出到子进程）。
    # 用 { …; } 分组保证即使 .env 缺失也不中断链路。
    #
    # 关键：pipeline 要「写」库，必须用写角色。webapi 的 quantmine_web 是只读角色
    # （AI query_database 的安全边界，靠它写不了数据表），用它写会 permission denied。
    # 故若 .env 配了 QUANTMINE_PIPELINE_DATABASE_URL（指向 quantmine_pipeline 写角色）
    # 就覆盖 QUANTMINE_DATABASE_URL；未配则退回原值（保持向后兼容）。
    command = (
        f'cd "{PROJECT_ROOT}" && '
        '{ set -a; [ -f .env ] && . ./.env; set +a; } && '
        'export QUANTMINE_DATABASE_URL="${QUANTMINE_PIPELINE_DATABASE_URL:-$QUANTMINE_DATABASE_URL}" && '
        f'"{PYTHON_BIN}" pipelines/{script} '
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
    t6 = BashOperator(
        task_id="attribution",
        bash_command=task_command("task_attribution.py", uses_config=True),
    )

t1 >> t2 >> t3 >> t4
t4 >> [task_save_market_bars, t5]
t5 >> t6

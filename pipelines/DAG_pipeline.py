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
# 解释器在 **运行时** 由 shell 解析, 不在解析期读 os.environ。
#
# 原来是 os.environ.get("QUANT_PYTHON_BIN", "python")，那是在 dag-processor 解析
# DAG 时求值的；而 dag-processor 只从 systemd unit 拿到 AIRFLOW_HOME，不读 .env。
# 于是 .env 里配的 QUANT_PYTHON_BIN 永远进不来，命令里被写死成 "python" —— 而 WSL
# 里根本没有 python（只有 python3），每个 task 都以 exit 127 / command not found 失败。
# 命令串里的 `. ./.env` 是 bash 运行时才执行的，救不了一个解析期就定死的值。
#
# 写成 shell 展开后，.env 先被 source，再决定用哪个解释器；缺省值指向仓库自带的
# venv（此时 cwd 已 cd 到 PROJECT_ROOT），所以不配任何环境变量也能跑。
PYTHON_BIN_EXPR = '"${QUANT_PYTHON_BIN:-.venv/bin/python}"'
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
        # WSL commonly receives only the proxy client's HTTP endpoint.  HTTPS
        # destinations (Wikipedia and Yahoo) still use that CONNECT proxy, but
        # urllib/curl-cffi require it to be advertised as https_proxy too.
        'export https_proxy="${https_proxy:-$http_proxy}" && '
        'export HTTP_PROXY="${HTTP_PROXY:-$http_proxy}" && '
        'export HTTPS_PROXY="${HTTPS_PROXY:-$https_proxy}" && '
        'export QUANTMINE_DATABASE_URL="${QUANTMINE_PIPELINE_DATABASE_URL:-$QUANTMINE_DATABASE_URL}" && '
        f'{PYTHON_BIN_EXPR} pipelines/{script} '
        # Airflow 3 manual runs created without an explicit logical date do not
        # expose the legacy ``ds`` template variable. ``run_after`` exists for
        # scheduled and manual runs alike, so the UI/API trigger path remains
        # renderable as well as the daily schedule.
        '--date {{ dag_run.run_after | ds }} --batch {{ run_id }}'
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
        # 这条 pipeline 的任务通过固定文件名交接中间产物（data/processed/*.partNN
        # .parquet），而清洗步骤会消费掉分片。Airflow 默认允许 16 个并发 run，两个
        # run 一起跑就会互相删文件，后一个的 data_cleaning 报 FileNotFoundError。
        # 新用户很容易造出这种情况：启用 DAG 会立刻触发一次到期的调度运行，此时
        # 再手动点一次「触发」就是两个并发 run。
        max_active_runs=1,
        tags=['quant_factor_mining'],
        ) as dag:
    t0 = BashOperator(
        task_id="universe_refresh",
        bash_command=task_command("task_0_universe.py"),
    )
    t1 = BashOperator(
        task_id="data_downloading",
        bash_command=task_command("task_1.py"),
        # all_done, 不是默认的 all_success: 成分股刷新失败(维基抓不到、代理不通、
        # 版面改了)不该拖垮当日行情下载。task_1 会退回 index_membership 里已有的
        # 区间表, 最坏情况是用昨天的成分股多跑一天, 远好过整条链路停摆。
        # t0 自己失败时仍会红, 该告警照样告警。
        trigger_rule="all_done",
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

t0 >> t1 >> t2 >> t3 >> t4
t4 >> [task_save_market_bars, t5]
t5 >> t6

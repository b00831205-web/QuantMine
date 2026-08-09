"""通过 Airflow CLI 执行变更操作（暂停 / 触发）。

为什么用 CLI 而不是直接写 SQLite：airflow.db 在 WSL drvfs 上，普通读写连接会
"unable to open database file"；且经由 CLI 走的是 Airflow 正式流程，语义正确、能被
调度器/执行器正常拾取。

元数据库已迁到 Postgres（见 airflow.cfg 的 sql_alchemy_conn），CLI 默认即走该库，
无需再重定向到 SQLite。

环境变量：
    QUANT_AIRFLOW_BIN     airflow 可执行文件。默认 ``<项目根>/.venv/bin/airflow``
                          （本项目 scheduler 即从此 venv 运行）。
    QUANT_AIRFLOW_PYTHON  运行任务级写操作脚本的 python。默认同 venv 的 python。
    AIRFLOW_HOME          Airflow 主目录。默认 ``<项目根>/airflow``（airflow.cfg 所在）。
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[5]
_DEFAULT_BIN = _PROJECT_ROOT / ".venv" / "bin" / "airflow"
_DEFAULT_PYTHON = _PROJECT_ROOT / ".venv" / "bin" / "python"
_DEFAULT_HOME = _PROJECT_ROOT / "airflow"
_TASK_ACTION_SCRIPT = Path(__file__).resolve().parent / "_airflow_task_action.py"


class AirflowCliError(RuntimeError):
    """airflow CLI 不可用或返回非零。"""


def _airflow_bin() -> str:
    return os.environ.get("QUANT_AIRFLOW_BIN", str(_DEFAULT_BIN))


def _airflow_python() -> str:
    return os.environ.get("QUANT_AIRFLOW_PYTHON", str(_DEFAULT_PYTHON))


def _airflow_env() -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("AIRFLOW_HOME", str(_DEFAULT_HOME))
    # 元数据库连接由 airflow.cfg（sql_alchemy_conn → Postgres）决定，此处不再覆盖。
    return env


def run(*args: str, timeout: float = 60.0) -> str:
    """执行 ``airflow <args>``，成功返回 stdout；失败抛 AirflowCliError。"""
    cmd = [_airflow_bin(), *args]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_airflow_env(),
        )
    except FileNotFoundError as exc:
        raise AirflowCliError(
            f"未找到 airflow 可执行文件：{_airflow_bin()}；可用 QUANT_AIRFLOW_BIN 指定"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise AirflowCliError(f"airflow {' '.join(args)} 超时（{timeout}s）") from exc

    if proc.returncode != 0:
        raise AirflowCliError(
            (proc.stderr.strip() or proc.stdout.strip() or "airflow CLI 返回非零")
        )
    return proc.stdout


def run_task_action(dag_id: str, run_id: str, task_id: str, action: str, timeout: float = 90.0) -> dict:
    """执行任务级写操作（clear / mark-success / mark-failed）。

    通过 Airflow venv 的 python 跑 `_airflow_task_action.py`（该脚本用 Airflow ORM
    直接改 task_instance 状态）。返回脚本最后一行的 JSON dict。
    """
    cmd = [_airflow_python(), str(_TASK_ACTION_SCRIPT), dag_id, run_id, task_id, action]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, env=_airflow_env()
        )
    except FileNotFoundError as exc:
        raise AirflowCliError(f"未找到 python：{_airflow_python()}") from exc
    except subprocess.TimeoutExpired as exc:
        raise AirflowCliError(f"任务操作超时（{timeout}s）") from exc

    if proc.returncode != 0:
        raise AirflowCliError(proc.stderr.strip() or proc.stdout.strip() or "任务操作失败")

    # 脚本会打印 Airflow 日志到 stderr，结果 JSON 在 stdout 最后一行。
    last = ""
    for line in proc.stdout.splitlines():
        if line.strip():
            last = line.strip()
    try:
        return json.loads(last)
    except (json.JSONDecodeError, ValueError) as exc:
        raise AirflowCliError(f"无法解析任务操作输出：{last!r}") from exc

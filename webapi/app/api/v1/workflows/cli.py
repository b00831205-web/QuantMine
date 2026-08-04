"""通过 Airflow CLI 执行变更操作（暂停 / 触发）。

为什么用 CLI 而不是直接写 SQLite：airflow.db 在 WSL drvfs 上，普通读写连接会
"unable to open database file"；且经由 CLI 走的是 Airflow 正式流程，语义正确、能被
调度器/执行器正常拾取。

环境变量：
    QUANT_AIRFLOW_BIN   airflow 可执行文件路径。默认 ``<项目根>/.venv/bin/airflow``
                        （本项目 scheduler 即从此 venv 运行）。
    AIRFLOW_HOME        Airflow 主目录。默认 ``<项目根>/airflow``（airflow.cfg 所在）。
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[5]
_DEFAULT_BIN = _PROJECT_ROOT / ".venv" / "bin" / "airflow"
_DEFAULT_HOME = _PROJECT_ROOT / "airflow"


class AirflowCliError(RuntimeError):
    """airflow CLI 不可用或返回非零。"""


def _airflow_bin() -> str:
    return os.environ.get("QUANT_AIRFLOW_BIN", str(_DEFAULT_BIN))


def _airflow_env() -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("AIRFLOW_HOME", str(_DEFAULT_HOME))
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

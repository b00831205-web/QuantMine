"""Airflow 元数据库（SQLite）连接助手。

设计要点：
- 路径解析：优先环境变量 ``QUANT_AIRFLOW_DB``；否则从本文件推导项目根下的
  ``airflow/airflow.db``（`parents[5]` = 项目根，见下方注释）。
- 只读路径：以 ``mode=ro&immutable=1`` URI 打开。项目里 airflow.db 落在 WSL 的
  drvfs 挂载盘（/mnt/e）上，普通读写连接会 "unable to open database file"（drvfs
  不支持 SQLite 需要的文件锁/shm）；``immutable=1`` 绕过加锁与 WAL 直接读主库文件。
  数据可能略滞后于未 checkpoint 的 WAL，对“看板式”读取可接受。
- 写路径（暂停/触发）不走这里，改用 airflow CLI（见 cli.py），更稳且语义正确。
- 每次请求开一个短连接并及时关闭；`row_factory` 设为 ``sqlite3.Row`` 便于按列名取值。
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

# webapi/app/api/v1/workflows/db.py → parents: [0]workflows [1]v1 [2]api [3]app
# [4]webapi [5]项目根。WSL 下 __file__ = /mnt/e/.../webapi/... 亦成立。
_PROJECT_ROOT = Path(__file__).resolve().parents[5]
_DEFAULT_DB = _PROJECT_ROOT / "airflow" / "airflow.db"


def airflow_db_path() -> Path:
    """返回 Airflow 元数据库文件路径（不保证存在）。"""
    override = os.environ.get("QUANT_AIRFLOW_DB")
    return Path(override) if override else _DEFAULT_DB


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """打开一个到 Airflow 元数据库的短连接（Row 工厂），退出时关闭。

    Raises:
        FileNotFoundError: 数据库文件不存在时抛出，交由上层转成 503/UPSTREAM。
    """
    path = airflow_db_path()
    if not path.exists():
        raise FileNotFoundError(str(path))
    # 只读 + immutable：drvfs 上唯一稳定可用的打开方式。
    uri = f"file:{path.as_posix()}?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True, timeout=5.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

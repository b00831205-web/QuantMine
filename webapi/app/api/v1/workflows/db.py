"""Helpers for connecting to the Airflow metadata database (Postgres).

历史：早期 Airflow 元数据库是放在 /mnt/e（WSL 的 9p/drvfs 挂载）上的 SQLite。
9p 不支持 SQLite 需要的文件锁：读要 ``immutable=1`` 绕锁，写（trigger/pause，经
airflow CLI）会直接 "unable to open database file"。现已把 Airflow 元数据库迁到
Postgres（airflow 库/角色），读写都走 pg，CLI 写路径也随 airflow.cfg 指向 pg。

设计要点：
- 连接串来自环境变量 ``QUANT_AIRFLOW_PG_DSN``（libpq DSN 或 URL），例如
  ``postgresql://airflow:***@localhost:5432/airflow``。
- ``connect()`` 返回一个薄封装 ``_PgConnection``，暴露 service.py 沿用的
  ``execute(sql, params)`` 接口：把 ``?`` 占位符换成 psycopg2 的 ``%s``，并用
  RealDictCursor 让按列名取值（``row["col"]``）与原 sqlite3.Row 行为一致。
- 只读会话；连接失败/未配置一律转成 ``FileNotFoundError``，沿用上层 503 映射
  （见 router 的 ``_guard_db``）。
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

import psycopg2
from psycopg2.extras import RealDictCursor


class _PgConnection:
    """Wrap a psycopg2 connection into the sqlite3-style ``execute`` interface expected by service.py."""

    def __init__(self, conn: "psycopg2.extensions.connection") -> None:
        self._conn = conn

    def execute(self, sql: str, params: tuple = ()):
        """Run one query and return a cursor (``fetchall``/``fetchone`` yield dict rows).

        service.py 沿用 sqlite3 的 ``?`` 占位符；这里统一转成 psycopg2 的 ``%s``。
        本域全部为字面 SQL，不含真正的问号字面量，替换是安全的。
        """
        cur = self._conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(sql.replace("?", "%s"), params)
        return cur

    def close(self) -> None:
        self._conn.close()


def _dsn() -> str:
    dsn = os.environ.get("QUANT_AIRFLOW_PG_DSN")
    if not dsn:
        raise RuntimeError(
            "未配置 QUANT_AIRFLOW_PG_DSN（Airflow 元数据库连接串），"
            "例如 postgresql://airflow:PW@localhost:5432/airflow"
        )
    return dsn


@contextmanager
def connect() -> Iterator[_PgConnection]:
    """Open a short read-only connection to the Airflow metadata database (Postgres), closed on exit.

    Raises:
        FileNotFoundError: 未配置连接串或数据库不可达；交由上层转成 503。
    """
    try:
        conn = psycopg2.connect(_dsn())
    except (psycopg2.OperationalError, RuntimeError) as exc:
        raise FileNotFoundError(f"Airflow metadata database unreachable: {exc}") from exc
    conn.set_session(readonly=True, autocommit=True)
    try:
        yield _PgConnection(conn)
    finally:
        conn.close()

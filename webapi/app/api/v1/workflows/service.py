"""workflows 域的读/写逻辑（直接操作 Airflow SQLite 元数据库）。"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from .db import connect
from .schemas import DagListItem, RunRef

# 列表页每个 DAG 展示的“最近运行”色块数量。
_RECENT_RUNS_LIMIT = 10


def _parse_dt(value: object) -> datetime | None:
    """把 SQLite 里存的时间戳字符串解析成 datetime；失败返回 None。

    Airflow 存的形如 ``2026-08-04 18:16:11.995168`` 或带 ``+00:00`` 偏移。
    """
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip().replace(" ", "T", 1)
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _duration_ms(start: datetime | None, end: datetime | None) -> int | None:
    if start is None or end is None:
        return None
    delta = (end - start).total_seconds()
    return int(delta * 1000) if delta >= 0 else None


def _split_owners(raw: object) -> list[str]:
    if not raw:
        return []
    # Airflow 用逗号分隔 owners。
    return [o.strip() for o in str(raw).split(",") if o.strip()]


def _row_to_run(row: sqlite3.Row) -> RunRef:
    start = _parse_dt(row["start_date"])
    end = _parse_dt(row["end_date"])
    return RunRef(
        run_id=row["run_id"],
        state=row["state"],
        run_type=row["run_type"],
        logical_date=_parse_dt(row["logical_date"]),
        start_date=start,
        end_date=end,
        duration_ms=_duration_ms(start, end),
    )


def _recent_runs(conn: sqlite3.Connection, dag_id: str) -> list[RunRef]:
    cur = conn.execute(
        """
        SELECT run_id, state, run_type, logical_date, start_date, end_date
        FROM dag_run
        WHERE dag_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (dag_id, _RECENT_RUNS_LIMIT),
    )
    return [_row_to_run(r) for r in cur.fetchall()]


def _tags(conn: sqlite3.Connection, dag_id: str) -> list[str]:
    cur = conn.execute(
        "SELECT name FROM dag_tag WHERE dag_id = ? ORDER BY name", (dag_id,)
    )
    return [r["name"] for r in cur.fetchall()]


def list_dags() -> list[DagListItem]:
    """返回所有“活跃”DAG（``is_stale = 0``，即 DAG 文件仍存在）。

    Airflow 会把文件已删除的 DAG 标记为 stale 并从列表页隐藏；示例 DAG 在本环境
    均为 stale，故该过滤天然只保留项目自有 DAG。
    """
    with connect() as conn:
        dag_rows = conn.execute(
            """
            SELECT dag_id, is_paused, dag_display_name, description, owners,
                   timetable_summary, next_dagrun
            FROM dag
            WHERE is_stale = 0
            ORDER BY dag_id
            """
        ).fetchall()

        items: list[DagListItem] = []
        for d in dag_rows:
            dag_id = d["dag_id"]
            recent = _recent_runs(conn, dag_id)
            items.append(
                DagListItem(
                    dag_id=dag_id,
                    display_name=d["dag_display_name"] or dag_id,
                    is_paused=bool(d["is_paused"]),
                    description=d["description"],
                    owners=_split_owners(d["owners"]),
                    tags=_tags(conn, dag_id),
                    schedule_summary=d["timetable_summary"],
                    next_run=_parse_dt(d["next_dagrun"]),
                    last_run=recent[0] if recent else None,
                    recent_runs=recent,
                )
            )
        return items


def dag_exists(dag_id: str) -> bool:
    with connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM dag WHERE dag_id = ? AND is_stale = 0", (dag_id,)
        ).fetchone()
        return row is not None

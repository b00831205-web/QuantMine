"""workflows 域的读/写逻辑（直接操作 Airflow SQLite 元数据库）。"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from .db import connect
from .schemas import (
    CodeResponse,
    DagDetail,
    DagListItem,
    GraphEdge,
    GraphNode,
    GraphResponse,
    GridResponse,
    GridRun,
    RunRef,
    RunsPage,
    TaskInstanceInfo,
)

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


# ─────────────────────────── 第二页：DAG 详情 ───────────────────────────


def get_dag_detail(dag_id: str) -> DagDetail | None:
    with connect() as conn:
        d = conn.execute(
            """
            SELECT dag_id, is_paused, dag_display_name, description, owners,
                   timetable_summary, timetable_description, next_dagrun, fileloc
            FROM dag
            WHERE dag_id = ? AND is_stale = 0
            """,
            (dag_id,),
        ).fetchone()
        if d is None:
            return None
        recent = _recent_runs(conn, dag_id)
        return DagDetail(
            dag_id=dag_id,
            display_name=d["dag_display_name"] or dag_id,
            is_paused=bool(d["is_paused"]),
            description=d["description"],
            owners=_split_owners(d["owners"]),
            tags=_tags(conn, dag_id),
            schedule_summary=d["timetable_summary"],
            timetable_description=d["timetable_description"],
            fileloc=d["fileloc"],
            next_run=_parse_dt(d["next_dagrun"]),
            last_run=recent[0] if recent else None,
            recent_runs=recent,
        )


def _unwrap(node: object) -> dict:
    """Airflow 序列化 JSON 里对象包成 {'__var':..., '__type':...}，取内层。"""
    if isinstance(node, dict) and "__var" in node:
        inner = node["__var"]
        return inner if isinstance(inner, dict) else {}
    return node if isinstance(node, dict) else {}


def _serialized_tasks(conn: sqlite3.Connection, dag_id: str) -> list[dict]:
    row = conn.execute(
        "SELECT data FROM serialized_dag WHERE dag_id = ? ORDER BY last_updated DESC LIMIT 1",
        (dag_id,),
    ).fetchone()
    if row is None or row["data"] is None:
        return []
    raw = row["data"]
    payload = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
    dag = payload.get("dag", payload)
    return [_unwrap(t) for t in dag.get("tasks", [])]


def _topo_order(task_ids: list[str], edges: list[tuple[str, str]]) -> list[str]:
    """Kahn 拓扑排序（上游在前）；有环/异常时回退到原顺序。"""
    indeg = {t: 0 for t in task_ids}
    adj: dict[str, list[str]] = {t: [] for t in task_ids}
    for src, dst in edges:
        if src in adj and dst in indeg:
            adj[src].append(dst)
            indeg[dst] += 1
    queue = [t for t in task_ids if indeg[t] == 0]
    order: list[str] = []
    while queue:
        node = queue.pop(0)
        order.append(node)
        for nxt in adj[node]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)
    return order if len(order) == len(task_ids) else task_ids


def _graph_parts(conn: sqlite3.Connection, dag_id: str) -> tuple[list[str], list[tuple[str, str]], dict[str, str]]:
    """返回 (task_ids, edges, labels)。"""
    tasks = _serialized_tasks(conn, dag_id)
    task_ids: list[str] = []
    labels: dict[str, str] = {}
    edges: list[tuple[str, str]] = []
    for t in tasks:
        tid = t.get("task_id")
        if not tid:
            continue
        task_ids.append(tid)
        labels[tid] = t.get("task_display_name") or tid
        for down in t.get("downstream_task_ids") or []:
            edges.append((tid, down))
    return task_ids, edges, labels


def get_graph(dag_id: str) -> GraphResponse:
    with connect() as conn:
        task_ids, edges, labels = _graph_parts(conn, dag_id)
    ordered = _topo_order(task_ids, edges)
    return GraphResponse(
        nodes=[GraphNode(id=t, label=labels.get(t, t)) for t in ordered],
        edges=[GraphEdge(source=s, target=d) for s, d in edges],
    )


def get_grid(dag_id: str, limit: int = 25) -> GridResponse:
    """最近 N 次运行 × 各任务状态（网格视图 + 图视图着色数据源）。"""
    with connect() as conn:
        task_ids, edges, _ = _graph_parts(conn, dag_id)
        ordered = _topo_order(task_ids, edges)

        run_rows = conn.execute(
            """
            SELECT run_id, state, run_type, logical_date, start_date, end_date
            FROM dag_run WHERE dag_id = ? ORDER BY id DESC LIMIT ?
            """,
            (dag_id, limit),
        ).fetchall()
        run_ids = [r["run_id"] for r in run_rows]

        # 一次性拉取这些运行的所有任务实例，避免 N+1。
        states: dict[tuple[str, str], str | None] = {}
        if run_ids:
            placeholders = ",".join("?" for _ in run_ids)
            ti_rows = conn.execute(
                f"""
                SELECT run_id, task_id, state FROM task_instance
                WHERE dag_id = ? AND run_id IN ({placeholders})
                """,
                (dag_id, *run_ids),
            ).fetchall()
            for ti in ti_rows:
                states[(ti["run_id"], ti["task_id"])] = ti["state"]

        runs: list[GridRun] = []
        for r in run_rows:
            start = _parse_dt(r["start_date"])
            end = _parse_dt(r["end_date"])
            runs.append(
                GridRun(
                    run_id=r["run_id"],
                    state=r["state"],
                    run_type=r["run_type"],
                    logical_date=_parse_dt(r["logical_date"]),
                    start_date=start,
                    end_date=end,
                    duration_ms=_duration_ms(start, end),
                    task_states={t: states.get((r["run_id"], t)) for t in ordered},
                )
            )
    return GridResponse(task_ids=ordered, runs=runs)


def get_run_tasks(dag_id: str, run_id: str) -> list[TaskInstanceInfo]:
    """某次运行的任务实例（按拓扑顺序，含未生成实例的任务占位）——甘特图数据源。"""
    with connect() as conn:
        task_ids, edges, _ = _graph_parts(conn, dag_id)
        order = _topo_order(task_ids, edges)
        rows = conn.execute(
            """
            SELECT task_id, state, start_date, end_date, duration, try_number
            FROM task_instance WHERE dag_id = ? AND run_id = ?
            """,
            (dag_id, run_id),
        ).fetchall()
        by_id = {r["task_id"]: r for r in rows}

        result: list[TaskInstanceInfo] = []
        for tid in order:
            r = by_id.get(tid)
            if r is None:
                result.append(TaskInstanceInfo(task_id=tid))
                continue
            start = _parse_dt(r["start_date"])
            end = _parse_dt(r["end_date"])
            dur = (
                int(r["duration"] * 1000)
                if r["duration"] is not None
                else _duration_ms(start, end)
            )
            result.append(
                TaskInstanceInfo(
                    task_id=tid,
                    state=r["state"],
                    start_date=start,
                    end_date=end,
                    duration_ms=dur,
                    try_number=r["try_number"] or 0,
                )
            )
        return result


def list_runs(dag_id: str, page: int, page_size: int) -> RunsPage:
    with connect() as conn:
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM dag_run WHERE dag_id = ?", (dag_id,)
        ).fetchone()["n"]
        rows = conn.execute(
            """
            SELECT run_id, state, run_type, logical_date, start_date, end_date
            FROM dag_run WHERE dag_id = ?
            ORDER BY id DESC LIMIT ? OFFSET ?
            """,
            (dag_id, page_size, (page - 1) * page_size),
        ).fetchall()
    return RunsPage(
        items=[_row_to_run(r) for r in rows],
        total=int(total),
        page=page,
        page_size=page_size,
    )


def get_code(dag_id: str) -> CodeResponse | None:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT fileloc, source_code FROM dag_code
            WHERE dag_id = ? ORDER BY last_updated DESC LIMIT 1
            """,
            (dag_id,),
        ).fetchone()
    if row is None:
        return None
    return CodeResponse(
        dag_id=dag_id,
        fileloc=row["fileloc"],
        source_code=row["source_code"] or "",
    )

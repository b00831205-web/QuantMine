"""workflows 路由：DAG 列表 / 暂停开关 / 触发。

- 读（列表）：只读 Airflow SQLite 元数据库。
- 写（暂停 / 触发）：经 airflow CLI（见 cli.py），环境需能访问项目 .venv 的 airflow。
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Body, HTTPException, Path, Query

from . import service
from .cli import AirflowCliError, run as airflow_cli, run_task_action
from .schemas import (
    CodeResponse,
    DagDetail,
    DagListItem,
    GraphResponse,
    GridResponse,
    PauseResponse,
    RunsPage,
    TaskActionResponse,
    TaskInstanceInfo,
    TriggerResponse,
)

_TASK_ACTIONS = {"clear", "mark-success", "mark-failed"}

router = APIRouter()


def _guard_db(exc: FileNotFoundError) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail=(
            f"Airflow 元数据库不可达：{exc}. "
            "请检查环境变量 QUANT_AIRFLOW_PG_DSN（Postgres 连接串）"
        ),
    )


@router.get("/workflows", response_model=list[DagListItem], summary="DAG 列表")
def get_workflows() -> list[DagListItem]:
    """返回所有活跃 DAG 及其最近运行状态（供列表页表格与色块渲染）。"""
    try:
        return service.list_dags()
    except FileNotFoundError as exc:
        raise _guard_db(exc) from exc


@router.get(
    "/workflows/{dag_id}",
    response_model=DagDetail,
    summary="DAG 详情（元信息）",
)
def get_workflow_detail(dag_id: str = Path(...)) -> DagDetail:
    try:
        detail = service.get_dag_detail(dag_id)
    except FileNotFoundError as exc:
        raise _guard_db(exc) from exc
    if detail is None:
        raise HTTPException(status_code=404, detail=f"DAG 不存在：{dag_id}")
    return detail


@router.get(
    "/workflows/{dag_id}/graph",
    response_model=GraphResponse,
    summary="DAG 拓扑（图视图）",
)
def get_workflow_graph(dag_id: str = Path(...)) -> GraphResponse:
    _ensure_dag(dag_id)
    return service.get_graph(dag_id)


@router.get(
    "/workflows/{dag_id}/grid",
    response_model=GridResponse,
    summary="网格视图（运行 × 任务状态）",
)
def get_workflow_grid(
    dag_id: str = Path(...),
    limit: int = Query(25, ge=1, le=100),
) -> GridResponse:
    _ensure_dag(dag_id)
    return service.get_grid(dag_id, limit)


@router.get(
    "/workflows/{dag_id}/runs/{run_id}/tasks",
    response_model=list[TaskInstanceInfo],
    summary="某次运行的任务实例（甘特图）",
)
def get_run_tasks(dag_id: str = Path(...), run_id: str = Path(...)) -> list[TaskInstanceInfo]:
    _ensure_dag(dag_id)
    return service.get_run_tasks(dag_id, run_id)


@router.get(
    "/workflows/{dag_id}/runs",
    response_model=RunsPage,
    summary="运行记录（分页）",
)
def get_workflow_runs(
    dag_id: str = Path(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
) -> RunsPage:
    _ensure_dag(dag_id)
    return service.list_runs(dag_id, page, page_size)


@router.get(
    "/workflows/{dag_id}/code",
    response_model=CodeResponse,
    summary="DAG 源码",
)
def get_workflow_code(dag_id: str = Path(...)) -> CodeResponse:
    _ensure_dag(dag_id)
    code = service.get_code(dag_id)
    if code is None:
        raise HTTPException(status_code=404, detail=f"未找到 DAG 源码：{dag_id}")
    return code


def _ensure_dag(dag_id: str) -> None:
    try:
        exists = service.dag_exists(dag_id)
    except FileNotFoundError as exc:
        raise _guard_db(exc) from exc
    if not exists:
        raise HTTPException(status_code=404, detail=f"DAG 不存在：{dag_id}")


@router.post(
    "/workflows/{dag_id}/pause",
    response_model=PauseResponse,
    summary="切换 DAG 暂停状态",
)
def pause_workflow(
    dag_id: str = Path(...),
    paused: bool = Body(..., embed=True, description="true 暂停 / false 恢复"),
) -> PauseResponse:
    _ensure_dag(dag_id)
    subcommand = "pause" if paused else "unpause"
    try:
        airflow_cli("dags", subcommand, dag_id)
    except AirflowCliError as exc:
        raise HTTPException(status_code=502, detail=f"airflow dags {subcommand} 失败：{exc}") from exc
    return PauseResponse(dag_id=dag_id, is_paused=paused)


@router.post(
    "/workflows/{dag_id}/trigger",
    response_model=TriggerResponse,
    status_code=202,
    summary="手动触发 DAG",
)
def trigger_workflow(dag_id: str = Path(...)) -> TriggerResponse:
    """通过 ``airflow dags trigger`` 创建一次手动运行（由调度器/执行器实际拉起）。"""
    _ensure_dag(dag_id)
    run_id = f"manual__{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+00:00')}"
    try:
        airflow_cli("dags", "trigger", dag_id, "--run-id", run_id)
    except AirflowCliError as exc:
        raise HTTPException(status_code=502, detail=f"airflow dags trigger 失败：{exc}") from exc
    return TriggerResponse(dag_id=dag_id, run_id=run_id, state="queued")


@router.post(
    "/workflows/{dag_id}/runs/{run_id}/tasks/{task_id}/{action}",
    response_model=TaskActionResponse,
    status_code=202,
    summary="任务操作：清除重跑 / 标记成功 / 标记失败",
)
def task_action(
    dag_id: str = Path(...),
    run_id: str = Path(...),
    task_id: str = Path(...),
    action: str = Path(..., description="clear | mark-success | mark-failed"),
) -> TaskActionResponse:
    if action not in _TASK_ACTIONS:
        raise HTTPException(status_code=400, detail=f"不支持的操作：{action}")
    _ensure_dag(dag_id)
    try:
        result = run_task_action(dag_id, run_id, task_id, action)
    except AirflowCliError as exc:
        raise HTTPException(status_code=502, detail=f"任务操作失败：{exc}") from exc
    return TaskActionResponse(
        task_id=task_id,
        action=action,
        state=result.get("state"),
        altered=int(result.get("altered", 0)),
    )

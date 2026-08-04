"""workflows 路由：DAG 列表 / 暂停开关 / 触发。

- 读（列表）：只读 Airflow SQLite 元数据库。
- 写（暂停 / 触发）：经 airflow CLI（见 cli.py），环境需能访问项目 .venv 的 airflow。
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Body, HTTPException, Path

from . import service
from .cli import AirflowCliError, run as airflow_cli
from .schemas import DagListItem, PauseResponse, TriggerResponse

router = APIRouter()


def _guard_db(exc: FileNotFoundError) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail=(
            f"Airflow 元数据库不存在或不可读：{exc}. "
            "可设置环境变量 QUANT_AIRFLOW_DB 指向 airflow.db"
        ),
    )


@router.get("/workflows", response_model=list[DagListItem], summary="DAG 列表")
def get_workflows() -> list[DagListItem]:
    """返回所有活跃 DAG 及其最近运行状态（供列表页表格与色块渲染）。"""
    try:
        return service.list_dags()
    except FileNotFoundError as exc:
        raise _guard_db(exc) from exc


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

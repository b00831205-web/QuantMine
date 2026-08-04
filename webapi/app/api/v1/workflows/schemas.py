"""workflows 域的 Pydantic 契约（camelCase 别名，对齐前端类型）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

# Airflow 原始状态值（dag_run.state / task_instance.state），None 表示尚无状态。
RunState = str  # 'queued' | 'running' | 'success' | 'failed'
TaskState = str  # 'success' | 'failed' | 'running' | 'skipped' | 'upstream_failed' | ...


class RunRef(BaseModel):
    """一次 DAG 运行的精简引用（用于最近运行色块 / 上次运行）。"""

    run_id: str = Field(alias="runId")
    state: RunState | None = None
    run_type: str = Field(alias="runType")
    logical_date: datetime | None = Field(default=None, alias="logicalDate")
    start_date: datetime | None = Field(default=None, alias="startDate")
    end_date: datetime | None = Field(default=None, alias="endDate")
    duration_ms: int | None = Field(default=None, alias="durationMs")

    model_config = {"populate_by_name": True}


class DagListItem(BaseModel):
    """DAG 列表页一行。"""

    dag_id: str = Field(alias="dagId")
    display_name: str = Field(alias="displayName")
    is_paused: bool = Field(alias="isPaused")
    description: str | None = None
    owners: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    schedule_summary: str | None = Field(default=None, alias="scheduleSummary")
    next_run: datetime | None = Field(default=None, alias="nextRun")
    last_run: RunRef | None = Field(default=None, alias="lastRun")
    recent_runs: list[RunRef] = Field(default_factory=list, alias="recentRuns")

    model_config = {"populate_by_name": True}


class PauseResponse(BaseModel):
    dag_id: str = Field(alias="dagId")
    is_paused: bool = Field(alias="isPaused")

    model_config = {"populate_by_name": True}


class TriggerResponse(BaseModel):
    dag_id: str = Field(alias="dagId")
    run_id: str = Field(alias="runId")
    state: RunState = "queued"

    model_config = {"populate_by_name": True}

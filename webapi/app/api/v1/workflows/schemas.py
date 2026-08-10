"""Pydantic contracts for the workflows domain (camelCase aliases aligned with frontend types)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

# Airflow 原始状态值（dag_run.state / task_instance.state），None 表示尚无状态。
RunState = str  # 'queued' | 'running' | 'success' | 'failed'
TaskState = str  # 'success' | 'failed' | 'running' | 'skipped' | 'upstream_failed' | ...


class RunRef(BaseModel):
    """Compact reference to one DAG run (for recent run squares / last run)."""

    run_id: str = Field(alias="runId")
    state: RunState | None = None
    run_type: str = Field(alias="runType")
    logical_date: datetime | None = Field(default=None, alias="logicalDate")
    start_date: datetime | None = Field(default=None, alias="startDate")
    end_date: datetime | None = Field(default=None, alias="endDate")
    duration_ms: int | None = Field(default=None, alias="durationMs")

    model_config = {"populate_by_name": True}


class DagListItem(BaseModel):
    """One row of the DAG list page."""

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


class DagDetail(BaseModel):
    """Header metadata for the DAG detail page."""

    dag_id: str = Field(alias="dagId")
    display_name: str = Field(alias="displayName")
    is_paused: bool = Field(alias="isPaused")
    description: str | None = None
    owners: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    schedule_summary: str | None = Field(default=None, alias="scheduleSummary")
    timetable_description: str | None = Field(default=None, alias="timetableDescription")
    fileloc: str | None = None
    next_run: datetime | None = Field(default=None, alias="nextRun")
    last_run: RunRef | None = Field(default=None, alias="lastRun")
    recent_runs: list[RunRef] = Field(default_factory=list, alias="recentRuns")

    model_config = {"populate_by_name": True}


class GraphNode(BaseModel):
    id: str
    label: str


class GraphEdge(BaseModel):
    source: str
    target: str


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class GridRun(BaseModel):
    """One column of the grid view: a run plus per-task states."""

    run_id: str = Field(alias="runId")
    state: RunState | None = None
    run_type: str = Field(alias="runType")
    logical_date: datetime | None = Field(default=None, alias="logicalDate")
    start_date: datetime | None = Field(default=None, alias="startDate")
    end_date: datetime | None = Field(default=None, alias="endDate")
    duration_ms: int | None = Field(default=None, alias="durationMs")
    # taskId -> state（None 表示该任务在这次运行里尚无实例）
    task_states: dict[str, TaskState | None] = Field(default_factory=dict, alias="taskStates")

    model_config = {"populate_by_name": True}


class GridResponse(BaseModel):
    task_ids: list[str] = Field(alias="taskIds")
    runs: list[GridRun]

    model_config = {"populate_by_name": True}


class TaskInstanceInfo(BaseModel):
    """Time info of a single task instance within a run (Gantt chart data source)."""

    task_id: str = Field(alias="taskId")
    state: TaskState | None = None
    start_date: datetime | None = Field(default=None, alias="startDate")
    end_date: datetime | None = Field(default=None, alias="endDate")
    duration_ms: int | None = Field(default=None, alias="durationMs")
    try_number: int = Field(default=0, alias="tryNumber")

    model_config = {"populate_by_name": True}


class RunsPage(BaseModel):
    items: list[RunRef]
    total: int
    page: int
    page_size: int = Field(alias="pageSize")

    model_config = {"populate_by_name": True}


class CodeResponse(BaseModel):
    dag_id: str = Field(alias="dagId")
    fileloc: str | None = None
    source_code: str = Field(alias="sourceCode")

    model_config = {"populate_by_name": True}


class PauseResponse(BaseModel):
    dag_id: str = Field(alias="dagId")
    is_paused: bool = Field(alias="isPaused")

    model_config = {"populate_by_name": True}


class TaskActionResponse(BaseModel):
    task_id: str = Field(alias="taskId")
    action: str
    state: TaskState | None = None
    altered: int = 0

    model_config = {"populate_by_name": True}


class TriggerResponse(BaseModel):
    dag_id: str = Field(alias="dagId")
    run_id: str = Field(alias="runId")
    state: RunState = "queued"

    model_config = {"populate_by_name": True}

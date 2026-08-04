/** Airflow DAG 状态（聚合视图，非 Airflow 原始值） */
export type DagStatus = 'healthy' | 'failed' | 'running' | 'idle' | 'unknown';
import type{ Page } from './api'; 

export interface DagSummary {
  dagId: string;
  displayName: string;
  status: DagStatus;
  lastRunId: string | null;
  lastRunDate: string | null;
  durationMs: number | null;
  nextRunDate: string | null;
}

export interface DagRunSummary {
  runId: string;
  status: 'success' | 'failed' | 'running' | 'queued';
  dataDate: string | null;
  startTime: string;
  endTime: string | null;
}

export interface TaskInstance {
  taskId: string;
  status: 'success' | 'failed' | 'running' | 'skipped' | 'upstream_failed';
  startTime: string | null;
  endTime: string | null;
  durationMs: number | null;
  tryNumber: number;
}

/** DAG 拓扑：节点 + 连线（图视图数据源） */
export interface DagGraphNode {
  id: string;
  label: string;
}

export interface DagGraphEdge {
  source: string;
  target: string;
}

export interface DagGraph {
  nodes: DagGraphNode[];
  edges: DagGraphEdge[];
}

export type DagRunsPage = Page<DagRunSummary>;

/* ─── 列表页（第一页）契约：对齐 FastAPI /api/v1/workflows ─── */

/** 一次运行的精简引用（最近运行色块 / 上次运行）。 */
export interface RunRef {
  runId: string;
  state: string | null;
  runType: string;
  logicalDate: string | null;
  startDate: string | null;
  endDate: string | null;
  durationMs: number | null;
}

/** DAG 列表页一行。 */
export interface DagListItem {
  dagId: string;
  displayName: string;
  isPaused: boolean;
  description: string | null;
  owners: string[];
  tags: string[];
  scheduleSummary: string | null;
  nextRun: string | null;
  lastRun: RunRef | null;
  recentRuns: RunRef[];
}

export interface PauseResult {
  dagId: string;
  isPaused: boolean;
}

export interface TriggerResult {
  dagId: string;
  runId: string;
  state: string;
}

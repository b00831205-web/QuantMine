/** Airflow DAG 状态（聚合视图，非 Airflow 原始值） */
export type DagStatus = 'healthy' | 'failed' | 'running' | 'idle' | 'unknown';

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

import { http } from '@/api/http';
import type {
  DagRunSummary,
  DagRunsPage,
  DagSummary,
  TaskInstance,
  DagGraph,
  DagListItem,
  PauseResult,
  TriggerResult,
} from '@/types/workflow';

/* ─── 列表页（第一页）客户端 ─── */

/** GET /api/v1/workflows —— DAG 列表（含最近运行状态） */
export function fetchWorkflows(signal?: AbortSignal): Promise<DagListItem[]> {
  return http<DagListItem[]>('/api/v1/workflows', { signal });
}

/** POST /api/v1/workflows/{dagId}/pause —— 切换暂停状态 */
export function pauseDag(
  dagId: string,
  paused: boolean,
  signal?: AbortSignal,
): Promise<PauseResult> {
  return http<PauseResult>(`/api/v1/workflows/${dagId}/pause`, {
    method: 'POST',
    body: { paused },
    signal,
  });
}

/** POST /api/v1/workflows/{dagId}/trigger —— 手动触发一次运行 */
export function triggerWorkflow(dagId: string, signal?: AbortSignal): Promise<TriggerResult> {
  return http<TriggerResult>(`/api/v1/workflows/${dagId}/trigger`, {
    method: 'POST',
    signal,
  });
}

/** GET /api/v1/workflows —— DAG 列表与当前状态 */
export function fetchDagSummaries(signal?: AbortSignal): Promise<DagSummary[]> {
  return http<DagSummary[]>(
    '/api/v1/workflows',
{signal})
}

/** GET /api/v1/workflows/{dagId}/runs —— 历史运行（分页） */
export function fetchDagRuns(
  dagId: string,
  page: number,
  pageSize: number,
  signal?: AbortSignal,
): Promise<DagRunsPage> {
    return http<DagRunsPage>(
        `/api/v1/workflows/${dagId}/runs`,
        {query: {
            page,
            pageSize,
        }, signal
    },
    )
  // TODO(USER_LEARNING): 路径拼 ${dagId}，query 传 { page, pageSize }
}

/** GET /api/v1/workflows/{dagId}/runs/{runId}/tasks —— 某次运行的任务实例 */
export function fetchRunTasks(
  dagId: string,
  runId: string,
  signal?: AbortSignal,
): Promise<TaskInstance[]> {
    return http<TaskInstance[]>(
        `/api/v1/workflows/${dagId}/runs/${runId}/tasks`,
        {signal},
    )
}

/** POST /api/v1/workflows/{dagId}/trigger —— 触发 DAG */
export function triggerDag(dagId: string, signal?: AbortSignal): Promise<DagRunSummary> {
  return http<DagRunSummary>(
    `/api/v1/workflows/${dagId}/trigger`,
    {method : 'POST', signal}
  )
}

/** POST /api/v1/workflows/{dagId}/runs/{runId}/retry —— 重跑失败运行 */
export function retryRun(
  dagId: string,
  runId: string,
  signal?: AbortSignal,
): Promise<DagRunSummary> {
    return http<DagRunSummary>(
        `/api/v1/workflows/${dagId}/runs/${runId}/retry`,
        {method: 'POST', signal}
    )
}

export function fetchDagGraph(dagId: string, signal?: AbortSignal): Promise<DagGraph>{
  return http<DagGraph>(
    `/api/v1/workflows/${dagId}/graph`,
    {signal}
  )
}

export function updateTaskState(
  dagId: string,
  runId: string,
  taskId: string,
  action: 'clear' | 'mark-success' | 'mark-failed',
  signal? : AbortSignal,
): Promise<TaskInstance>{
  return http<TaskInstance>(
    `/api/v1/workflows/${dagId}/runs/${runId}/tasks/${taskId}/${action}`,
    {method: 'POST', signal}
  )
}

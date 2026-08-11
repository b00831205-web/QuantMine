import { useEffect, useMemo, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { PageHeader } from '@/components/common/PageHeader';
import { Card } from '@/components/common/Card';
import { AsyncBoundary } from '@/components/common/AsyncBoundary';
import { HttpError } from '@/api/http';
import {
  fetchWorkflowDetail,
  fetchDagGraph,
  fetchWorkflowGrid,
  fetchWorkflowRuns,
  fetchWorkflowCode,
  fetchRunTasks,
  pauseDag,
  triggerWorkflow,
  updateTaskState,
} from '@/api/client';
import type {
  DagDetail,
  DagGraph,
  GridResponse,
  WorkflowRunsPage,
  CodeResponse,
  TaskInstanceInfo,
} from '@/types/workflow';
import type { AsyncState } from '@/types/api';
import { DagGraphView } from '@/components/chart/DagGraph';
import { TaskBarChart } from '@/components/chart/TaskBarChart';
import { stateColor, stateLabel, CORE_LEGEND } from '@/utils/workflowStatus';
import { fmtDateTime, fmtDuration } from '@/utils/format';
import { Toggle } from '@/components/common/Toggle';
import { Play } from 'lucide-react';
import i18n from '@/i18n';

type TabKey = 'overview' | 'graph' | 'grid' | 'runs' | 'code';
const TABS: TabKey[] = ['overview', 'graph', 'grid', 'runs', 'code'];

const networkError = (): AsyncState<never> => ({
  status: 'error',
  error: {
    code: 'NETWORK_ERROR',
    title: i18n.t('common.networkError.title'),
    detail: i18n.t('common.networkError.detail'),
    status: 0,
  },
});

/** 通用：把一个 Promise 拉进 AsyncState（带 abort）。 */
function useAsync<T>(loader: (signal: AbortSignal) => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [state, setState] = useState<AsyncState<T>>({ status: 'idle' });
  useEffect(() => {
    const controller = new AbortController();
    setState({ status: 'loading' });
    loader(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setState({ status: 'success', data });
      })
      .catch((error) => {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        if (error instanceof HttpError) setState({ status: 'error', error: error.apiError });
        else setState(networkError());
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}

/** 状态标记：成功/失败用旗帜（绿旗/红旗），其余用圆点。 */
const StateMark = ({ state }: { state: string | null }) => {
  if (state === 'success' || state === 'failed') {
    return (
      <span style={{ color: stateColor(state), fontSize: 13, lineHeight: 1 }} aria-hidden>
        ⚑
      </span>
    );
  }
  return (
    <span style={{ width: 8, height: 8, borderRadius: '50%', background: stateColor(state) }} />
  );
};

const StateChip = ({ state }: { state: string | null }) => (
  <span
    style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 6,
      padding: '1px 8px',
      borderRadius: 999,
      border: `1px solid ${stateColor(state)}`,
      color: stateColor(state),
      fontSize: 12,
    }}
  >
    <StateMark state={state} />
    {stateLabel(state)}
  </span>
);

const Legend = () => {
  const { t } = useTranslation();
  return (
    <div
      style={{
        display: 'flex',
        gap: 'var(--sp-4)',
        flexWrap: 'wrap',
        marginTop: 'var(--sp-3)',
        fontSize: 'var(--fs-sm)',
        color: 'var(--text-muted)',
      }}
    >
      {CORE_LEGEND.map((l) => (
        <span key={l.state} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <span
            style={{ width: 12, height: 12, borderRadius: 3, background: stateColor(l.state) }}
          />
          {t(`workflow.state.${l.state}`, { defaultValue: l.label })}
        </span>
      ))}
    </div>
  );
};

const metaRow = (label: string, value: React.ReactNode) => (
  <div style={{ display: 'flex', gap: 'var(--sp-3)', padding: '4px 0' }}>
    <div style={{ width: 96, color: 'var(--text-muted)', fontSize: 'var(--fs-sm)', flexShrink: 0 }}>
      {label}
    </div>
    <div style={{ fontSize: 'var(--fs-sm)' }}>{value}</div>
  </div>
);

export const WorkflowDetailPage = () => {
  const { t } = useTranslation();
  const { dagId = '' } = useParams<{ dagId: string }>();
  const navigate = useNavigate();

  const [activeTab, setActiveTab] = useState<TabKey>('graph');
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [isPaused, setIsPaused] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmTrigger, setConfirmTrigger] = useState(false);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [runsPage, setRunsPage] = useState(1);
  const [gridRefresh, setGridRefresh] = useState(0);
  const [taskBusy, setTaskBusy] = useState<string | null>(null);
  const RUNS_PAGE_SIZE = 20;

  const detailState = useAsync<DagDetail>((s) => fetchWorkflowDetail(dagId, s), [dagId]);
  const graphState = useAsync<DagGraph>((s) => fetchDagGraph(dagId, s), [dagId]);
  const gridState = useAsync<GridResponse>(
    (s) => fetchWorkflowGrid(dagId, 25, s),
    [dagId, gridRefresh],
  );
  const codeState = useAsync<CodeResponse>((s) => fetchWorkflowCode(dagId, s), [dagId]);
  const runTasksState = useAsync<TaskInstanceInfo[]>(
    (s) => (selectedRunId ? fetchRunTasks(dagId, selectedRunId, s) : Promise.resolve([])),
    [dagId, selectedRunId, gridRefresh],
  );
  const runsState = useAsync<WorkflowRunsPage>(
    (s) => fetchWorkflowRuns(dagId, runsPage, RUNS_PAGE_SIZE, s),
    [dagId, runsPage],
  );

  // 详情就绪后同步暂停态；网格就绪后默认选中最新一次运行。
  useEffect(() => {
    if (detailState.status === 'success') setIsPaused(detailState.data.isPaused);
  }, [detailState]);
  useEffect(() => {
    if (
      gridState.status === 'success' &&
      selectedRunId === null &&
      gridState.data.runs.length > 0
    ) {
      setSelectedRunId(gridState.data.runs[0]!.runId);
    }
  }, [gridState, selectedRunId]);

  const grid = gridState.status === 'success' ? gridState.data : null;
  const selectedRun = grid?.runs.find((r) => r.runId === selectedRunId) ?? null;

  const runStats = useMemo(() => {
    const acc = { success: 0, failed: 0, running: 0, other: 0 };
    for (const r of grid?.runs ?? []) {
      if (r.state === 'success') acc.success += 1;
      else if (r.state === 'failed') acc.failed += 1;
      else if (r.state === 'running') acc.running += 1;
      else acc.other += 1;
    }
    return acc;
  }, [grid]);

  const handleTogglePause = async () => {
    if (isPaused === null) return;
    setBusy(true);
    setActionMsg(null);
    try {
      const res = await pauseDag(dagId, !isPaused);
      setIsPaused(res.isPaused);
    } catch (error) {
      setActionMsg(error instanceof HttpError ? error.apiError.title : t('workflow.pauseFailed'));
    } finally {
      setBusy(false);
    }
  };

  const handleTrigger = async () => {
    setBusy(true);
    setActionMsg(null);
    try {
      await triggerWorkflow(dagId);
      setActionMsg(t('workflowDetail.triggered'));
      setConfirmTrigger(false);
    } catch (error) {
      setActionMsg(error instanceof HttpError ? error.apiError.title : t('workflow.triggerFailed'));
      setConfirmTrigger(false);
    } finally {
      setBusy(false);
    }
  };

  const selectRunForGraph = (runId: string) => {
    setSelectedRunId(runId);
    setActiveTab('graph');
  };

  const TASK_ACTION_LABEL: Record<'mark-success' | 'mark-failed' | 'clear', string> = {
    'mark-success': t('workflowDetail.task.markSuccess'),
    'mark-failed': t('workflowDetail.task.markFailed'),
    clear: t('workflowDetail.task.clear'),
  };

  const runTaskAction = async (
    taskId: string,
    action: 'mark-success' | 'mark-failed' | 'clear',
  ) => {
    if (!selectedRunId) return;
    setTaskBusy(`${taskId}:${action}`);
    setActionMsg(null);
    try {
      await updateTaskState(dagId, selectedRunId, taskId, action);
      setActionMsg(t('workflowDetail.task.success', { taskId, action: TASK_ACTION_LABEL[action] }));
      setGridRefresh((k) => k + 1); // 刷新网格 → 图与任务面板重新着色
    } catch (error) {
      setActionMsg(
        error instanceof HttpError
          ? t('workflowDetail.task.failedWith', {
              action: TASK_ACTION_LABEL[action],
              detail: error.apiError.detail ?? error.apiError.title,
            })
          : t('workflowDetail.task.failed', { action: TASK_ACTION_LABEL[action] }),
      );
    } finally {
      setTaskBusy(null);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-5)' }}>
      <PageHeader
        title={detailState.status === 'success' ? detailState.data.displayName : dagId}
        subtitle={
          detailState.status === 'success'
            ? (detailState.data.description ?? t('workflowDetail.dagDetail'))
            : t('workflowDetail.dagDetail')
        }
        actions={
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-3)' }}>
            {isPaused !== null && (
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                <Toggle on={isPaused} disabled={busy} onChange={handleTogglePause} />
                <span style={{ fontSize: 'var(--fs-sm)', color: 'var(--text-muted)' }}>
                  {isPaused ? t('workflow.paused') : t('workflow.running')}
                </span>
              </span>
            )}
            <button type="button" disabled={busy} onClick={() => setConfirmTrigger(true)}>
              <Play size={11} strokeWidth={2} aria-hidden="true" /> {t('workflow.trigger')}
            </button>
            <button type="button" onClick={() => navigate('/workflows')}>
              {t('workflowDetail.backToList')}
            </button>
          </div>
        }
      />

      {actionMsg && (
        <div
          style={{
            padding: 'var(--sp-2) var(--sp-3)',
            background: 'var(--bg-surface-2)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-sm)',
            fontSize: 'var(--fs-sm)',
          }}
        >
          {actionMsg}
        </div>
      )}

      {/* 标签页 */}
      <div
        style={{
          display: 'flex',
          gap: 'var(--sp-1)',
          borderBottom: '1px solid var(--border-subtle)',
        }}
      >
        {TABS.map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => setActiveTab(key)}
            style={{
              padding: 'var(--sp-2) var(--sp-4)',
              background: 'transparent',
              border: 'none',
              borderBottom: activeTab === key ? '2px solid var(--accent)' : '2px solid transparent',
              color: activeTab === key ? 'var(--text-primary)' : 'var(--text-muted)',
              cursor: 'pointer',
              fontWeight: activeTab === key ? 600 : 400,
            }}
          >
            {t(`workflowDetail.tab.${key}`)}
          </button>
        ))}
      </div>

      {/* 概览 */}
      {activeTab === 'overview' && (
        <Card title={t('workflowDetail.tab.overview')}>
          <AsyncBoundary state={detailState} isEmpty={() => false} emptyTitle="">
            {(d) => (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--sp-5)' }}>
                <div>
                  {metaRow(t('workflowDetail.meta.description'), d.description ?? '—')}
                  {metaRow(t('workflowDetail.meta.schedule'), d.scheduleSummary ?? '—')}
                  {metaRow(t('workflowDetail.meta.timetable'), d.timetableDescription || '—')}
                  {metaRow(t('workflowDetail.meta.owner'), d.owners.join(', ') || '—')}
                  {metaRow(
                    t('workflowDetail.meta.tags'),
                    d.tags.length ? (
                      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                        {d.tags.map((t) => (
                          <span
                            key={t}
                            style={{
                              fontSize: 11,
                              color: 'var(--text-muted)',
                              border: '1px solid var(--border-subtle)',
                              borderRadius: 4,
                              padding: '0 6px',
                            }}
                          >
                            {t}
                          </span>
                        ))}
                      </div>
                    ) : (
                      '—'
                    ),
                  )}
                  {metaRow(
                    t('workflowDetail.meta.file'),
                    <span style={{ wordBreak: 'break-all' }}>{d.fileloc ?? '—'}</span>,
                  )}
                </div>
                <div>
                  {metaRow(
                    t('workflowDetail.meta.lastRun'),
                    d.lastRun ? (
                      <span style={{ display: 'inline-flex', gap: 8, alignItems: 'center' }}>
                        <StateChip state={d.lastRun.state} />
                        {fmtDateTime(d.lastRun.startDate)} · {fmtDuration(d.lastRun.durationMs)}
                      </span>
                    ) : (
                      t('workflow.notRun')
                    ),
                  )}
                  {metaRow(t('workflowDetail.meta.nextRun'), fmtDateTime(d.nextRun))}
                  {metaRow(
                    t('workflowDetail.meta.recentStats'),
                    <span style={{ display: 'inline-flex', gap: 8 }}>
                      <StateChip state="success" />
                      {runStats.success}
                      <StateChip state="failed" />
                      {runStats.failed}
                      <StateChip state="running" />
                      {runStats.running}
                    </span>,
                  )}
                  {metaRow(
                    t('workflowDetail.meta.recentRuns'),
                    <div style={{ display: 'flex', gap: 3 }}>
                      {(grid?.runs ?? [])
                        .slice(0, 10)
                        .reverse()
                        .map((r) => (
                          <span
                            key={r.runId}
                            title={`${r.runId}\n${stateLabel(r.state)}`}
                            onClick={() => selectRunForGraph(r.runId)}
                            style={{
                              width: 12,
                              height: 12,
                              borderRadius: 3,
                              background: stateColor(r.state),
                              cursor: 'pointer',
                            }}
                          />
                        ))}
                    </div>,
                  )}
                </div>
              </div>
            )}
          </AsyncBoundary>
        </Card>
      )}

      {/* 图视图 */}
      {activeTab === 'graph' && (
        <Card
          title={t('workflowDetail.tab.graph')}
          extra={
            grid && grid.runs.length > 0 ? (
              <select
                value={selectedRunId ?? ''}
                onChange={(e) => setSelectedRunId(e.target.value)}
                style={{
                  background: 'var(--bg-surface-2)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '4px 8px',
                }}
              >
                {grid.runs.map((r) => (
                  <option key={r.runId} value={r.runId}>
                    {stateLabel(r.state)} · {fmtDateTime(r.startDate ?? r.logicalDate)}
                  </option>
                ))}
              </select>
            ) : undefined
          }
        >
          <AsyncBoundary
            state={graphState}
            isEmpty={(g) => g.nodes.length === 0}
            emptyTitle={t('workflowDetail.graphEmpty')}
            emptyHint={t('workflowDetail.graphEmptyHint')}
          >
            {(g) => {
              const runLabel = selectedRun
                ? `${stateLabel(selectedRun.state)} · ${fmtDateTime(selectedRun.startDate ?? selectedRun.logicalDate)}`
                : t('workflowDetail.noRunSelected');
              return (
                <>
                  {/* 上：图（大） */}
                  <DagGraphView
                    graph={g}
                    height={440}
                    {...(selectedRun ? { taskStates: selectedRun.taskStates } : {})}
                  />
                  <Legend />

                  {/* 下：左甘特图 / 右任务操作 */}
                  <div
                    style={{
                      display: 'grid',
                      // minmax(0,…) 关键：否则 fr 轨道有隐式 min-width:auto，
                      // 右栏按钮会把它撑大，导致近似 1:1 而非 1:3。
                      gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 3fr)',
                      gap: 'var(--sp-5)',
                      marginTop: 'var(--sp-4)',
                    }}
                  >
                    {/* 左：任务耗时柱状图 */}
                    <div>
                      <div style={sectionTitle}>
                        {t('workflowDetail.taskDuration', { runLabel })}
                      </div>
                      <AsyncBoundary
                        state={runTasksState}
                        isEmpty={(rows) => rows.length === 0}
                        emptyTitle={t('workflowDetail.noRunSelected')}
                        emptyHint={t('workflowDetail.selectRunHint')}
                      >
                        {(rows) => <TaskBarChart tasks={rows} />}
                      </AsyncBoundary>
                    </div>

                    {/* 右：任务操作 */}
                    <div>
                      <div style={sectionTitle}>
                        {t('workflowDetail.taskActions', { runLabel })}
                      </div>
                      <div>
                        {g.nodes.map((n) => {
                          const st = selectedRun?.taskStates[n.id] ?? null;
                          return (
                            <div
                              key={n.id}
                              style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: 'var(--sp-2)',
                                height: TASK_ROW_H,
                                borderBottom: '1px solid var(--border-subtle)',
                              }}
                            >
                              <div
                                style={{
                                  flex: 1,
                                  whiteSpace: 'nowrap',
                                  overflow: 'hidden',
                                  textOverflow: 'ellipsis',
                                  fontSize: 'var(--fs-sm)',
                                }}
                                title={n.id}
                              >
                                {n.id}
                              </div>
                              <div style={{ width: 92, flexShrink: 0 }}>
                                <StateChip state={st} />
                              </div>
                              <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                                {(['mark-success', 'mark-failed', 'clear'] as const).map((a) => (
                                  <button
                                    key={a}
                                    type="button"
                                    disabled={!selectedRunId || taskBusy !== null}
                                    onClick={() => runTaskAction(n.id, a)}
                                    style={taskBtnStyle(a, !selectedRunId || taskBusy !== null)}
                                  >
                                    {taskBusy === `${n.id}:${a}` ? '…' : TASK_ACTION_LABEL[a]}
                                  </button>
                                ))}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                </>
              );
            }}
          </AsyncBoundary>
        </Card>
      )}

      {/* 网格 */}
      {activeTab === 'grid' && (
        <Card title={t('workflowDetail.gridTitle')}>
          <AsyncBoundary
            state={gridState}
            isEmpty={(g) => g.runs.length === 0}
            emptyTitle={t('workflowDetail.noRuns')}
            emptyHint={t('workflowDetail.triggerToSeeGrid')}
          >
            {(g) => {
              const cols = [...g.runs].reverse(); // 最新在右
              return (
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ borderCollapse: 'collapse' }}>
                    <thead>
                      <tr>
                        <th
                          style={{
                            padding: 'var(--sp-2)',
                            textAlign: 'left',
                            color: 'var(--text-muted)',
                            fontSize: 'var(--fs-sm)',
                            position: 'sticky',
                            left: 0,
                            background: 'var(--bg-surface)',
                          }}
                        >
                          {t('workflowDetail.taskVsRun')}
                        </th>
                        {cols.map((r) => (
                          <th
                            key={r.runId}
                            title={`${r.runId}\n${stateLabel(r.state)}`}
                            onClick={() => selectRunForGraph(r.runId)}
                            style={{ padding: '4px 3px', cursor: 'pointer' }}
                          >
                            <div
                              style={{
                                display: 'flex',
                                flexDirection: 'column',
                                alignItems: 'center',
                                gap: 3,
                              }}
                            >
                              <span
                                style={{
                                  width: 10,
                                  height: 10,
                                  borderRadius: '50%',
                                  background: stateColor(r.state),
                                }}
                              />
                              <span
                                style={{
                                  fontSize: 10,
                                  color: 'var(--text-muted)',
                                  writingMode: 'vertical-rl',
                                }}
                              >
                                {fmtDateTime(r.startDate ?? r.logicalDate).slice(5, 16)}
                              </span>
                            </div>
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {g.taskIds.map((tid) => (
                        <tr key={tid}>
                          <td
                            style={{
                              padding: 'var(--sp-2)',
                              fontSize: 'var(--fs-sm)',
                              whiteSpace: 'nowrap',
                              position: 'sticky',
                              left: 0,
                              background: 'var(--bg-surface)',
                              borderRight: '1px solid var(--border-subtle)',
                            }}
                          >
                            {tid}
                          </td>
                          {cols.map((r) => {
                            const st = r.taskStates[tid] ?? null;
                            return (
                              <td key={r.runId} style={{ padding: 3, textAlign: 'center' }}>
                                <span
                                  title={`${tid} · ${stateLabel(st)}`}
                                  style={{
                                    display: 'inline-block',
                                    width: 18,
                                    height: 18,
                                    borderRadius: 4,
                                    background: stateColor(st),
                                  }}
                                />
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <Legend />
                </div>
              );
            }}
          </AsyncBoundary>
        </Card>
      )}

      {/* 运行记录 */}
      {activeTab === 'runs' && (
        <Card title={t('workflowDetail.tab.runs')}>
          <AsyncBoundary
            state={runsState}
            isEmpty={(p) => p.items.length === 0}
            emptyTitle={t('workflowDetail.noRunRecords')}
            emptyHint={t('workflowDetail.triggerThenView')}
          >
            {(p) => {
              const totalPages = Math.max(1, Math.ceil(p.total / RUNS_PAGE_SIZE));
              return (
                <div>
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr>
                        {[
                          'workflowDetail.runCol.id',
                          'workflowDetail.runCol.type',
                          'workflowDetail.runCol.state',
                          'workflowDetail.runCol.logical',
                          'workflowDetail.runCol.start',
                          'workflowDetail.runCol.end',
                          'workflowDetail.runCol.duration',
                        ].map((key) => (
                          <th
                            key={key}
                            style={{
                              textAlign: 'left',
                              padding: 'var(--sp-2) var(--sp-3)',
                              color: 'var(--text-muted)',
                              fontSize: 'var(--fs-sm)',
                              fontWeight: 500,
                              borderBottom: '1px solid var(--border-subtle)',
                              whiteSpace: 'nowrap',
                            }}
                          >
                            {t(key)}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {p.items.map((r) => (
                        <tr key={r.runId}>
                          <td style={cellStyle}>
                            <button
                              type="button"
                              onClick={() => selectRunForGraph(r.runId)}
                              style={{
                                background: 'none',
                                border: 'none',
                                color: 'var(--accent)',
                                cursor: 'pointer',
                                padding: 0,
                                fontSize: 'var(--fs-sm)',
                                textAlign: 'left',
                              }}
                            >
                              {r.runId}
                            </button>
                          </td>
                          <td style={cellStyle}>{r.runType}</td>
                          <td style={cellStyle}>
                            <StateChip state={r.state} />
                          </td>
                          <td style={cellStyle}>{fmtDateTime(r.logicalDate)}</td>
                          <td style={cellStyle}>{fmtDateTime(r.startDate)}</td>
                          <td style={cellStyle}>{fmtDateTime(r.endDate)}</td>
                          <td style={cellStyle}>{fmtDuration(r.durationMs)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'flex-end',
                      alignItems: 'center',
                      gap: 'var(--sp-3)',
                      marginTop: 'var(--sp-3)',
                      fontSize: 'var(--fs-sm)',
                    }}
                  >
                    <span style={{ color: 'var(--text-muted)' }}>
                      {t('common.pagination', { total: p.total, page: p.page, pages: totalPages })}
                    </span>
                    <button
                      type="button"
                      disabled={runsPage <= 1}
                      onClick={() => setRunsPage((n) => Math.max(1, n - 1))}
                    >
                      {t('common.prevPage')}
                    </button>
                    <button
                      type="button"
                      disabled={runsPage >= totalPages}
                      onClick={() => setRunsPage((n) => n + 1)}
                    >
                      {t('common.nextPage')}
                    </button>
                  </div>
                </div>
              );
            }}
          </AsyncBoundary>
        </Card>
      )}

      {/* 代码 */}
      {activeTab === 'code' && (
        <Card title={t('workflowDetail.codeTitle')}>
          <AsyncBoundary state={codeState} isEmpty={() => false} emptyTitle="">
            {(c) => (
              <div>
                <div
                  style={{
                    color: 'var(--text-muted)',
                    fontSize: 'var(--fs-sm)',
                    marginBottom: 'var(--sp-2)',
                    wordBreak: 'break-all',
                  }}
                >
                  {c.fileloc}
                </div>
                <pre
                  style={{
                    margin: 0,
                    padding: 'var(--sp-3)',
                    background: 'var(--bg-surface-2)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-sm)',
                    overflowX: 'auto',
                    fontSize: 12,
                    lineHeight: 1.5,
                    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
                  }}
                >
                  {c.sourceCode}
                </pre>
              </div>
            )}
          </AsyncBoundary>
        </Card>
      )}

      {/* 触发确认 */}
      {confirmTrigger && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 100,
          }}
          onClick={() => setConfirmTrigger(false)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: 'var(--bg-surface)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-md)',
              padding: 'var(--sp-5)',
              width: 360,
            }}
          >
            <div style={{ fontWeight: 600, marginBottom: 'var(--sp-2)' }}>
              {t('workflow.confirmTitle')}
            </div>
            <div
              style={{
                color: 'var(--text-muted)',
                fontSize: 'var(--fs-sm)',
                marginBottom: 'var(--sp-4)',
              }}
            >
              {t('workflow.confirmDesc', { dagId })}
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--sp-2)' }}>
              <button type="button" disabled={busy} onClick={() => setConfirmTrigger(false)}>
                {t('workflow.cancel')}
              </button>
              <button type="button" disabled={busy} onClick={handleTrigger}>
                {busy ? t('workflow.submitting') : t('workflow.confirmTrigger')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

const cellStyle: React.CSSProperties = {
  padding: 'var(--sp-2) var(--sp-3)',
  borderBottom: '1px solid var(--border-subtle)',
  fontSize: 'var(--fs-sm)',
  whiteSpace: 'nowrap',
};

/** 任务操作列表每行行高。 */
const TASK_ROW_H = 44;

const sectionTitle: React.CSSProperties = {
  fontSize: 'var(--fs-sm)',
  color: 'var(--text-muted)',
  marginBottom: 'var(--sp-2)',
};

const TASK_BTN_COLOR: Record<'mark-success' | 'mark-failed' | 'clear', string> = {
  'mark-success': 'var(--positive)',
  'mark-failed': 'var(--negative)',
  clear: 'var(--text-muted)',
};

const taskBtnStyle = (
  action: 'mark-success' | 'mark-failed' | 'clear',
  disabled: boolean,
): React.CSSProperties => ({
  padding: '3px 8px',
  fontSize: 12,
  lineHeight: 1.4,
  borderRadius: 6,
  border: `1px solid ${TASK_BTN_COLOR[action]}`,
  background: 'transparent',
  color: TASK_BTN_COLOR[action],
  cursor: disabled ? 'not-allowed' : 'pointer',
  opacity: disabled ? 0.45 : 1,
  whiteSpace: 'nowrap',
});

import { useEffect, useMemo, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
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
  pauseDag,
  triggerWorkflow,
} from '@/api/client';
import type {
  DagDetail,
  DagGraph,
  GridResponse,
  WorkflowRunsPage,
  CodeResponse,
} from '@/types/workflow';
import type { AsyncState } from '@/types/api';
import { DagGraphView } from '@/components/chart/DagGraph';
import { stateColor, stateLabel, CORE_LEGEND } from '@/utils/workflowStatus';
import { fmtDateTime, fmtDuration } from '@/utils/format';
import { Toggle } from '@/components/common/Toggle';
import i18n from '@/i18n';

type TabKey = 'overview' | 'graph' | 'grid' | 'runs' | 'code';
const TABS: Array<{ key: TabKey; label: string }> = [
  { key: 'overview', label: '概览' },
  { key: 'graph', label: '图视图' },
  { key: 'grid', label: '网格' },
  { key: 'runs', label: '运行记录' },
  { key: 'code', label: '代码' },
];

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
function useAsync<T>(
  loader: (signal: AbortSignal) => Promise<T>,
  deps: unknown[],
): AsyncState<T> {
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
    <span
      style={{ width: 8, height: 8, borderRadius: '50%', background: stateColor(state) }}
    />
    {stateLabel(state)}
  </span>
);

const Legend = () => (
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
        {l.label}
      </span>
    ))}
  </div>
);

const metaRow = (label: string, value: React.ReactNode) => (
  <div style={{ display: 'flex', gap: 'var(--sp-3)', padding: '4px 0' }}>
    <div style={{ width: 96, color: 'var(--text-muted)', fontSize: 'var(--fs-sm)', flexShrink: 0 }}>
      {label}
    </div>
    <div style={{ fontSize: 'var(--fs-sm)' }}>{value}</div>
  </div>
);

export const WorkflowDetailPage = () => {
  const { dagId = '' } = useParams<{ dagId: string }>();
  const navigate = useNavigate();

  const [activeTab, setActiveTab] = useState<TabKey>('graph');
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [isPaused, setIsPaused] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmTrigger, setConfirmTrigger] = useState(false);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [runsPage, setRunsPage] = useState(1);
  const RUNS_PAGE_SIZE = 20;

  const detailState = useAsync<DagDetail>((s) => fetchWorkflowDetail(dagId, s), [dagId]);
  const graphState = useAsync<DagGraph>((s) => fetchDagGraph(dagId, s), [dagId]);
  const gridState = useAsync<GridResponse>((s) => fetchWorkflowGrid(dagId, 25, s), [dagId]);
  const codeState = useAsync<CodeResponse>((s) => fetchWorkflowCode(dagId, s), [dagId]);
  const runsState = useAsync<WorkflowRunsPage>(
    (s) => fetchWorkflowRuns(dagId, runsPage, RUNS_PAGE_SIZE, s),
    [dagId, runsPage],
  );

  // 详情就绪后同步暂停态；网格就绪后默认选中最新一次运行。
  useEffect(() => {
    if (detailState.status === 'success') setIsPaused(detailState.data.isPaused);
  }, [detailState]);
  useEffect(() => {
    if (gridState.status === 'success' && selectedRunId === null && gridState.data.runs.length > 0) {
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
      setActionMsg(error instanceof HttpError ? error.apiError.title : '暂停操作失败');
    } finally {
      setBusy(false);
    }
  };

  const handleTrigger = async () => {
    setBusy(true);
    setActionMsg(null);
    try {
      await triggerWorkflow(dagId);
      setActionMsg('已触发，稍后刷新查看运行');
      setConfirmTrigger(false);
    } catch (error) {
      setActionMsg(error instanceof HttpError ? error.apiError.title : '触发失败');
      setConfirmTrigger(false);
    } finally {
      setBusy(false);
    }
  };

  const selectRunForGraph = (runId: string) => {
    setSelectedRunId(runId);
    setActiveTab('graph');
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-5)' }}>
      <PageHeader
        title={detailState.status === 'success' ? detailState.data.displayName : dagId}
        subtitle={
          detailState.status === 'success'
            ? detailState.data.description ?? 'DAG 详情'
            : 'DAG 详情'
        }
        actions={
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-3)' }}>
            {isPaused !== null && (
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                <Toggle on={isPaused} disabled={busy} onChange={handleTogglePause} />
                <span style={{ fontSize: 'var(--fs-sm)', color: 'var(--text-muted)' }}>
                  {isPaused ? '已暂停' : '运行中'}
                </span>
              </span>
            )}
            <button type="button" disabled={busy} onClick={() => setConfirmTrigger(true)}>
              ▶ 触发
            </button>
            <button type="button" onClick={() => navigate('/workflows')}>
              ← 返回列表
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
      <div style={{ display: 'flex', gap: 'var(--sp-1)', borderBottom: '1px solid var(--border-subtle)' }}>
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setActiveTab(t.key)}
            style={{
              padding: 'var(--sp-2) var(--sp-4)',
              background: 'transparent',
              border: 'none',
              borderBottom:
                activeTab === t.key ? '2px solid var(--accent)' : '2px solid transparent',
              color: activeTab === t.key ? 'var(--text-primary)' : 'var(--text-muted)',
              cursor: 'pointer',
              fontWeight: activeTab === t.key ? 600 : 400,
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* 概览 */}
      {activeTab === 'overview' && (
        <Card title="概览">
          <AsyncBoundary state={detailState} isEmpty={() => false} emptyTitle="">
            {(d) => (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--sp-5)' }}>
                <div>
                  {metaRow('描述', d.description ?? '—')}
                  {metaRow('调度', d.scheduleSummary ?? '—')}
                  {metaRow('调度说明', d.timetableDescription || '—')}
                  {metaRow('Owner', d.owners.join(', ') || '—')}
                  {metaRow(
                    '标签',
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
                  {metaRow('文件', <span style={{ wordBreak: 'break-all' }}>{d.fileloc ?? '—'}</span>)}
                </div>
                <div>
                  {metaRow(
                    '上次运行',
                    d.lastRun ? (
                      <span style={{ display: 'inline-flex', gap: 8, alignItems: 'center' }}>
                        <StateChip state={d.lastRun.state} />
                        {fmtDateTime(d.lastRun.startDate)} · {fmtDuration(d.lastRun.durationMs)}
                      </span>
                    ) : (
                      '尚未运行'
                    ),
                  )}
                  {metaRow('下次运行', fmtDateTime(d.nextRun))}
                  {metaRow(
                    '近期统计',
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
                    '最近运行',
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
          title="图视图"
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
            emptyTitle="该 DAG 暂无拓扑"
            emptyHint="确认 serialized_dag 有数据"
          >
            {(g) => (
              <>
                <DagGraphView
                  graph={g}
                  height={440}
                  {...(selectedRun ? { taskStates: selectedRun.taskStates } : {})}
                />
                <Legend />
              </>
            )}
          </AsyncBoundary>
        </Card>
      )}

      {/* 网格 */}
      {activeTab === 'grid' && (
        <Card title="网格视图（运行 × 任务）">
          <AsyncBoundary
            state={gridState}
            isEmpty={(g) => g.runs.length === 0}
            emptyTitle="暂无运行"
            emptyHint="触发一次运行后查看网格"
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
                          任务 \ 运行
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
        <Card title="运行记录">
          <AsyncBoundary
            state={runsState}
            isEmpty={(p) => p.items.length === 0}
            emptyTitle="暂无运行记录"
            emptyHint="触发一次运行后查看"
          >
            {(p) => {
              const totalPages = Math.max(1, Math.ceil(p.total / RUNS_PAGE_SIZE));
              return (
                <div>
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr>
                        {['运行 ID', '类型', '状态', '逻辑日期', '开始', '结束', '时长'].map((h) => (
                          <th
                            key={h}
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
                            {h}
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
                      共 {p.total} 条 · 第 {p.page} / {totalPages} 页
                    </span>
                    <button
                      type="button"
                      disabled={runsPage <= 1}
                      onClick={() => setRunsPage((n) => Math.max(1, n - 1))}
                    >
                      上一页
                    </button>
                    <button
                      type="button"
                      disabled={runsPage >= totalPages}
                      onClick={() => setRunsPage((n) => n + 1)}
                    >
                      下一页
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
        <Card title="DAG 源码">
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
            <div style={{ fontWeight: 600, marginBottom: 'var(--sp-2)' }}>确认触发该 DAG？</div>
            <div
              style={{ color: 'var(--text-muted)', fontSize: 'var(--fs-sm)', marginBottom: 'var(--sp-4)' }}
            >
              {dagId} · 将创建一次手动运行
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--sp-2)' }}>
              <button type="button" disabled={busy} onClick={() => setConfirmTrigger(false)}>
                取消
              </button>
              <button type="button" disabled={busy} onClick={handleTrigger}>
                {busy ? '提交中…' : '确认触发'}
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

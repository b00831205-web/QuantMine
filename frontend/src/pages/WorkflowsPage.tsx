import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { PageHeader } from '@/components/common/PageHeader';
import { Card } from '@/components/common/Card';
import { AsyncBoundary } from '@/components/common/AsyncBoundary';
import { HttpError } from '@/api/http';
import { fetchWorkflows, pauseDag, triggerWorkflow } from '@/api/client';
import type { DagListItem, RunRef } from '@/types/workflow';
import type { AsyncState } from '@/types/api';
import { stateColor, stateLabel, CORE_LEGEND } from '@/utils/workflowStatus';
import { fmtDateTime, fmtDuration } from '@/utils/format';
import { Toggle } from '@/components/common/Toggle';
import i18n from '@/i18n';

type StateFilter = 'all' | 'running' | 'success' | 'failed' | 'paused';

const FILTERS: Array<{ key: StateFilter; label: string }> = [
  { key: 'all', label: '全部' },
  { key: 'running', label: '运行中' },
  { key: 'success', label: '成功' },
  { key: 'failed', label: '失败' },
  { key: 'paused', label: '已暂停' },
];

const RECENT_SQUARES = 10;

const networkError = (): AsyncState<never> => ({
  status: 'error',
  error: {
    code: 'NETWORK_ERROR',
    title: i18n.t('common.networkError.title'),
    detail: i18n.t('common.networkError.detail'),
    status: 0,
  },
});

/* ── 最近运行色块 ── */
const RecentRuns = ({ runs }: { runs: RunRef[] }) => {
  if (runs.length === 0) {
    return <span style={{ color: 'var(--text-muted)', fontSize: 'var(--fs-sm)' }}>尚未运行</span>;
  }
  // 后端按新→旧返回；反转成时间顺序，最新在最右（与 Airflow 一致）。
  const ordered = [...runs].slice(0, RECENT_SQUARES).reverse();
  return (
    <div style={{ display: 'flex', gap: 3, alignItems: 'center' }}>
      {ordered.map((r) => (
        <span
          key={r.runId}
          title={`${r.runId}\n${stateLabel(r.state)} · ${fmtDuration(r.durationMs)}`}
          style={{
            width: 12,
            height: 12,
            borderRadius: 3,
            background: stateColor(r.state),
            display: 'inline-block',
          }}
        />
      ))}
    </div>
  );
};

const StateDot = ({ state }: { state: string | null }) => (
  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
    <span
      style={{
        width: 9,
        height: 9,
        borderRadius: '50%',
        background: stateColor(state),
        display: 'inline-block',
      }}
    />
    <span>{stateLabel(state)}</span>
  </span>
);

const thStyle: React.CSSProperties = {
  textAlign: 'left',
  padding: 'var(--sp-2) var(--sp-3)',
  color: 'var(--text-muted)',
  fontSize: 'var(--fs-sm)',
  fontWeight: 500,
  borderBottom: '1px solid var(--border-subtle)',
  whiteSpace: 'nowrap',
};

const tdStyle: React.CSSProperties = {
  padding: 'var(--sp-3)',
  borderBottom: '1px solid var(--border-subtle)',
  verticalAlign: 'middle',
  fontSize: 'var(--fs-sm)',
};

export const WorkflowsPage = () => {
  const navigate = useNavigate();
  const [listState, setListState] = useState<AsyncState<DagListItem[]>>({ status: 'idle' });
  const [refreshKey, setRefreshKey] = useState(0);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<StateFilter>('all');
  const [busyDagId, setBusyDagId] = useState<string | null>(null);
  const [confirmTrigger, setConfirmTrigger] = useState<string | null>(null);
  const [actionMsg, setActionMsg] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setListState({ status: 'loading' });
    fetchWorkflows(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setListState({ status: 'success', data });
      })
      .catch((error) => {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        if (error instanceof HttpError) {
          setListState({ status: 'error', error: error.apiError });
          return;
        }
        setListState(networkError());
      });
    return () => controller.abort();
  }, [refreshKey]);

  const dags = listState.status === 'success' ? listState.data : [];

  const summary = useMemo(() => {
    let running = 0;
    let failed = 0;
    let paused = 0;
    for (const d of dags) {
      if (d.isPaused) paused += 1;
      if (d.lastRun?.state === 'running') running += 1;
      if (d.lastRun?.state === 'failed') failed += 1;
    }
    return { total: dags.length, running, failed, paused };
  }, [dags]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return dags.filter((d) => {
      if (q && !d.displayName.toLowerCase().includes(q) && !d.dagId.toLowerCase().includes(q)) {
        return false;
      }
      switch (filter) {
        case 'paused':
          return d.isPaused;
        case 'running':
          return d.lastRun?.state === 'running';
        case 'success':
          return d.lastRun?.state === 'success';
        case 'failed':
          return d.lastRun?.state === 'failed';
        default:
          return true;
      }
    });
  }, [dags, search, filter]);

  const patchDag = (dagId: string, patch: Partial<DagListItem>) => {
    setListState((prev) =>
      prev.status === 'success'
        ? { status: 'success', data: prev.data.map((d) => (d.dagId === dagId ? { ...d, ...patch } : d)) }
        : prev,
    );
  };

  const handleTogglePause = async (dag: DagListItem) => {
    setBusyDagId(dag.dagId);
    setActionMsg(null);
    try {
      const res = await pauseDag(dag.dagId, !dag.isPaused);
      patchDag(dag.dagId, { isPaused: res.isPaused });
    } catch (error) {
      setActionMsg(error instanceof HttpError ? error.apiError.title : '暂停操作失败');
    } finally {
      setBusyDagId(null);
    }
  };

  const handleConfirmTrigger = async () => {
    if (confirmTrigger === null) return;
    const dagId = confirmTrigger;
    setBusyDagId(dagId);
    setActionMsg(null);
    try {
      await triggerWorkflow(dagId);
      setActionMsg(`已触发 ${dagId}，稍候刷新查看运行`);
      setConfirmTrigger(null);
      setRefreshKey((k) => k + 1);
    } catch (error) {
      setActionMsg(error instanceof HttpError ? error.apiError.title : '触发失败');
      setConfirmTrigger(null);
    } finally {
      setBusyDagId(null);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-5)' }}>
      <PageHeader
        title="Airflow 工作流"
        subtitle="DAG 列表 · 数据来自 Airflow 元数据库（只读）"
        actions={
          <button type="button" onClick={() => setRefreshKey((k) => k + 1)}>
            刷新
          </button>
        }
      />

      {/* 工具栏 */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--sp-3)',
          flexWrap: 'wrap',
        }}
      >
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="搜索 DAG 名称 / ID"
          style={{
            padding: 'var(--sp-2) var(--sp-3)',
            background: 'var(--bg-surface-2)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-sm)',
            color: 'var(--text-primary)',
            minWidth: 220,
          }}
        />
        <div style={{ display: 'flex', gap: 'var(--sp-1)' }}>
          {FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              onClick={() => setFilter(f.key)}
              style={{
                padding: 'var(--sp-1) var(--sp-3)',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border-subtle)',
                background: filter === f.key ? 'var(--accent)' : 'transparent',
                color: filter === f.key ? '#fff' : 'var(--text-primary)',
                cursor: 'pointer',
              }}
            >
              {f.label}
            </button>
          ))}
        </div>
        <div style={{ flex: 1 }} />
        <div style={{ color: 'var(--text-muted)', fontSize: 'var(--fs-sm)' }}>
          {summary.total} 个 DAG · {summary.running} 运行中 · {summary.failed} 失败 · {summary.paused} 暂停
        </div>
      </div>

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

      <Card title="DAGs">
        <AsyncBoundary
          state={listState}
          isEmpty={() => filtered.length === 0}
          emptyTitle={dags.length === 0 ? '暂无活跃 DAG' : '无匹配 DAG'}
          emptyHint={
            dags.length === 0
              ? '确认后端 /api/v1/workflows 可读取 Airflow 元数据库'
              : '调整搜索或筛选条件'
          }
        >
          {() => (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr>
                    <th style={thStyle}>暂停</th>
                    <th style={thStyle}>DAG</th>
                    <th style={thStyle}>最近运行</th>
                    <th style={thStyle}>上次运行</th>
                    <th style={thStyle}>下次运行</th>
                    <th style={thStyle}>调度</th>
                    <th style={{ ...thStyle, textAlign: 'right' }}>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((dag) => (
                    <tr
                      key={dag.dagId}
                      onClick={() => navigate(`/workflows/${dag.dagId}`)}
                      style={{ cursor: 'pointer' }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--bg-surface-2)')}
                      onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                    >
                      <td style={tdStyle}>
                        <Toggle
                          on={dag.isPaused}
                          disabled={busyDagId === dag.dagId}
                          onChange={() => handleTogglePause(dag)}
                        />
                      </td>
                      <td style={tdStyle}>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                          <span style={{ color: 'var(--accent)', fontWeight: 600 }}>
                            {dag.displayName}
                          </span>
                          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                            {dag.tags.map((t) => (
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
                        </div>
                      </td>
                      <td style={tdStyle}>
                        <RecentRuns runs={dag.recentRuns} />
                      </td>
                      <td style={tdStyle}>
                        {dag.lastRun ? (
                          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                            <StateDot state={dag.lastRun.state} />
                            <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>
                              {fmtDateTime(dag.lastRun.startDate)}
                            </span>
                          </div>
                        ) : (
                          <span style={{ color: 'var(--text-muted)' }}>尚未运行</span>
                        )}
                      </td>
                      <td style={tdStyle}>{fmtDateTime(dag.nextRun)}</td>
                      <td style={tdStyle}>{dag.scheduleSummary ?? '—'}</td>
                      <td style={{ ...tdStyle, textAlign: 'right' }}>
                        <button
                          type="button"
                          disabled={busyDagId === dag.dagId}
                          onClick={(e) => {
                            e.stopPropagation();
                            setConfirmTrigger(dag.dagId);
                          }}
                        >
                          ▶ 触发
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </AsyncBoundary>

        {/* 图例：状态 → 颜色 */}
        <div
          style={{
            display: 'flex',
            gap: 'var(--sp-4)',
            flexWrap: 'wrap',
            marginTop: 'var(--sp-3)',
            paddingTop: 'var(--sp-3)',
            borderTop: '1px solid var(--border-subtle)',
            fontSize: 'var(--fs-sm)',
            color: 'var(--text-muted)',
          }}
        >
          {CORE_LEGEND.map((l) => (
            <span key={l.state} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <span
                style={{
                  width: 12,
                  height: 12,
                  borderRadius: 3,
                  background: stateColor(l.state),
                  display: 'inline-block',
                }}
              />
              {l.label}
            </span>
          ))}
        </div>
      </Card>

      {/* 触发确认弹窗 */}
      {confirmTrigger !== null && (
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
          onClick={() => setConfirmTrigger(null)}
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
              {confirmTrigger} · 将创建一次手动运行
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--sp-2)' }}>
              <button
                type="button"
                disabled={busyDagId === confirmTrigger}
                onClick={() => setConfirmTrigger(null)}
              >
                取消
              </button>
              <button
                type="button"
                disabled={busyDagId === confirmTrigger}
                onClick={handleConfirmTrigger}
              >
                {busyDagId === confirmTrigger ? '提交中…' : '确认触发'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

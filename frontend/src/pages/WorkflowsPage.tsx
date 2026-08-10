/**
 * Airflow 工作流页 · Evidence Ledger（证据账本）
 *
 * 方向契约：
 * THESIS：DAG 表格是页面唯一的主证据区，页面性格来自一套统一按钮体系，
 *         而非整块钴蓝填充的筛选按钮。
 * OWN-WORLD：沿用 DESIGN.md 的哑光深色研究终端语言——平层色阶、1px 细线、
 *         钴蓝只留给主要动作、选中与焦点；图标统一为描边 SVG。
 * STORY：研究员扫读 DAG 健康度，翻转暂停开关，通过主次分明的确认弹窗触发运行。
 * FIRST VIEWPORT：页头（刷新动作）+ 筛选工具条 + 带边框 DAG 表格 + 状态图例。
 * FORM：Evidence Ledger，与市场总览 / 调仓收益 template 同构。
 * FINISH：unreviewed and undocumented is unfinished；本次以类型/测试/构建与人工视觉复核收口。
 */

import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { PageHeader } from '@/components/common/PageHeader';
import { AsyncBoundary } from '@/components/common/AsyncBoundary';
import { HttpError } from '@/api/http';
import { fetchWorkflows, pauseDag, triggerWorkflow } from '@/api/client';
import type { DagListItem, RunRef } from '@/types/workflow';
import type { AsyncState } from '@/types/api';
import { stateColor, CORE_LEGEND } from '@/utils/workflowStatus';
import { fmtDateTime, fmtDuration } from '@/utils/format';
import { Toggle } from '@/components/common/Toggle';
import { Play, RotateCcw } from 'lucide-react';
import i18n from '@/i18n';
import styles from './WorkflowsPage.module.css';

type StateFilter = 'all' | 'running' | 'success' | 'failed' | 'paused';

const FILTERS: StateFilter[] = ['all', 'running', 'success', 'failed', 'paused'];

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

/** 状态 → i18n 文案；未知状态回退到原始值 */
const stateLabel = (state: string | null | undefined, t: TFunction) =>
  t(`workflow.state.${state ?? 'none'}`, { defaultValue: state ?? '' });

/* ── 最近运行色块 ── */
const RecentRuns = ({ runs }: { runs: RunRef[] }) => {
  const { t } = useTranslation();
  if (runs.length === 0) {
    return <span className={styles.notRun}>{t('workflow.notRun')}</span>;
  }
  // 后端按新→旧返回；反转成时间顺序，最新在最右（与 Airflow 一致）。
  const ordered = [...runs].slice(0, RECENT_SQUARES).reverse();
  return (
    <span className={styles.runs}>
      {ordered.map((r) => (
        <span
          key={r.runId}
          title={`${r.runId}\n${stateLabel(r.state, t)} · ${fmtDuration(r.durationMs)}`}
          className={styles.runSquare}
          style={{ background: stateColor(r.state) }}
        />
      ))}
    </span>
  );
};

const StateDot = ({ state }: { state: string | null }) => {
  const { t } = useTranslation();
  return (
    <span className={styles.state}>
      <span className={styles.stateDot} style={{ background: stateColor(state) }} />
      <span>{stateLabel(state, t)}</span>
    </span>
  );
};

export const WorkflowsPage = () => {
  const { t } = useTranslation();
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

  const dags = useMemo(() => (listState.status === 'success' ? listState.data : []), [listState]);

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
        ? {
            status: 'success',
            data: prev.data.map((d) => (d.dagId === dagId ? { ...d, ...patch } : d)),
          }
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
      setActionMsg(error instanceof HttpError ? error.apiError.title : t('workflow.pauseFailed'));
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
      setActionMsg(t('workflow.triggered', { dagId }));
      setConfirmTrigger(null);
      setRefreshKey((k) => k + 1);
    } catch (error) {
      setActionMsg(error instanceof HttpError ? error.apiError.title : t('workflow.triggerFailed'));
      setConfirmTrigger(null);
    } finally {
      setBusyDagId(null);
    }
  };

  return (
    <div className={styles.page}>
      <div className={styles.headerWrap}>
        <PageHeader
          title={t('nav.workflows')}
          subtitle={t('workflow.subtitle')}
          actions={
            <button
              type="button"
              className={styles.refreshBtn}
              onClick={() => setRefreshKey((k) => k + 1)}
            >
              <RotateCcw size={12} strokeWidth={1.75} aria-hidden="true" />
              {t('workflow.refresh')}
            </button>
          }
        />
      </div>

      <div className={styles.toolbar}>
        <input
          type="text"
          className={styles.search}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={t('workflow.searchPlaceholder')}
          aria-label={t('workflow.searchPlaceholder')}
        />
        <div className={styles.filters} role="group" aria-label={t('workflow.filterGroup')}>
          {FILTERS.map((f) => (
            <button
              key={f}
              type="button"
              className={filter === f ? styles.filterActive : styles.filterBtn}
              aria-pressed={filter === f}
              onClick={() => setFilter(f)}
            >
              {t(`workflow.filter.${f}`)}
            </button>
          ))}
        </div>
        <div className={styles.summary}>
          {t('workflow.summary', {
            total: summary.total,
            running: summary.running,
            failed: summary.failed,
            paused: summary.paused,
          })}
        </div>
      </div>

      {actionMsg ? (
        <div className={styles.notice} role="status">
          <span className={styles.noticeDot} aria-hidden="true" />
          {actionMsg}
        </div>
      ) : null}

      <section className={styles.panel} aria-label={t('workflow.dagsTitle')}>
        <div className={styles.panelHead}>
          <h2>{t('workflow.dagsTitle')}</h2>
          <span className={styles.count}>{t('workflow.count', { count: dags.length })}</span>
        </div>

        <AsyncBoundary
          state={listState}
          isEmpty={() => filtered.length === 0}
          emptyTitle={dags.length === 0 ? t('workflow.emptyNoDags') : t('workflow.emptyNoMatch')}
          emptyHint={dags.length === 0 ? t('workflow.emptyHint') : t('workflow.emptyHintFilter')}
        >
          {() => (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>{t('workflow.col.paused')}</th>
                    <th>{t('workflow.col.dag')}</th>
                    <th>{t('workflow.col.recent')}</th>
                    <th>{t('workflow.col.last')}</th>
                    <th>{t('workflow.col.next')}</th>
                    <th>{t('workflow.col.schedule')}</th>
                    <th className={styles.opsHead}>{t('workflow.col.ops')}</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((dag) => (
                    <tr
                      key={dag.dagId}
                      className={styles.row}
                      onClick={() => navigate(`/workflows/${dag.dagId}`)}
                    >
                      <td>
                        <span className={styles.switchCell}>
                          <Toggle
                            on={dag.isPaused}
                            disabled={busyDagId === dag.dagId}
                            onChange={() => handleTogglePause(dag)}
                          />
                          <span className={dag.isPaused ? styles.pausedLabel : styles.runningLabel}>
                            {dag.isPaused ? t('workflow.paused') : t('workflow.running')}
                          </span>
                        </span>
                      </td>
                      <td>
                        <div className={styles.dagCell}>
                          <span className={styles.dagName}>{dag.displayName}</span>
                          <div className={styles.tagRow}>
                            {dag.tags.map((tag) => (
                              <span key={tag} className={styles.tag}>
                                {tag}
                              </span>
                            ))}
                          </div>
                        </div>
                      </td>
                      <td>
                        <RecentRuns runs={dag.recentRuns} />
                      </td>
                      <td>
                        {dag.lastRun ? (
                          <div className={styles.lastRunCell}>
                            <StateDot state={dag.lastRun.state} />
                            <span className={styles.lastRunTime}>
                              {fmtDateTime(dag.lastRun.startDate)}
                            </span>
                          </div>
                        ) : (
                          <span className={styles.notRun}>{t('workflow.notRun')}</span>
                        )}
                      </td>
                      <td className={styles.mono}>{fmtDateTime(dag.nextRun)}</td>
                      <td className={styles.mono}>{dag.scheduleSummary ?? '—'}</td>
                      <td className={styles.ops}>
                        <button
                          type="button"
                          className={styles.triggerBtn}
                          disabled={busyDagId === dag.dagId}
                          onClick={(e) => {
                            e.stopPropagation();
                            setConfirmTrigger(dag.dagId);
                          }}
                        >
                          <Play size={11} strokeWidth={2} aria-hidden="true" />
                          {t('workflow.trigger')}
                        </button>
                        <button
                          type="button"
                          className={styles.viewBtn}
                          onClick={(e) => {
                            e.stopPropagation();
                            navigate(`/workflows/${dag.dagId}`);
                          }}
                        >
                          {t('workflow.view')}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </AsyncBoundary>

        <div className={styles.legend}>
          {CORE_LEGEND.map((l) => (
            <span key={l.state}>
              <span
                className={styles.legendDot}
                style={{ background: stateColor(l.state) }}
                aria-hidden="true"
              />
              {stateLabel(l.state, t)}
            </span>
          ))}
        </div>
      </section>

      {confirmTrigger !== null ? (
        <div className={styles.overlay} onClick={() => setConfirmTrigger(null)}>
          <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
            <div className={styles.modalTitle}>{t('workflow.confirmTitle')}</div>
            <div className={styles.modalDesc}>
              {t('workflow.confirmDesc', { dagId: confirmTrigger })}
            </div>
            <div className={styles.modalActions}>
              <button
                type="button"
                className={styles.ghostBtn}
                disabled={busyDagId === confirmTrigger}
                onClick={() => setConfirmTrigger(null)}
              >
                {t('workflow.cancel')}
              </button>
              <button
                type="button"
                className={styles.primaryBtn}
                disabled={busyDagId === confirmTrigger}
                onClick={handleConfirmTrigger}
              >
                {busyDagId === confirmTrigger ? (
                  <>
                    <span className={styles.spinner} aria-hidden="true" />
                    {t('workflow.submitting')}
                  </>
                ) : (
                  <>
                    <Play size={11} strokeWidth={2} aria-hidden="true" />
                    {t('workflow.confirmTrigger')}
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <p className={styles.footnote}>
        For research and educational purposes only. Not investment advice. Past performance does not
        guarantee future results.
      </p>
    </div>
  );
};

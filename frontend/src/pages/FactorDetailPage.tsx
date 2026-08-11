/**
 * 因子详情页 · Evidence Ledger（证据账本）
 *
 * 方向契约：
 * THESIS：IC 时序是页面唯一的主证据区；持有期 tab 收进同一面板头，
 *         选中周期的统计落在图下账本，统计表与回测架构成其下的次级证据。
 * OWN-WORLD：沿用 DESIGN.md 的哑光深色研究终端语言——平层色阶、1px 细线、
 *         钴蓝只用于选中/焦点/显著性；机器值一律等宽数字；显著性用
 *         单点 + 中性/钴蓝文字，不用红绿。
 * STORY：研究员选定上下文与周期，读 IC 序列与其统计账本，扫全周期表，
 *         再在回测卡下展开净值曲线。
 * FIRST VIEWPORT：返回链 + 因子标题 + 上下文工具条 + 单块 IC 面板
 *         （头 + 周期分段 + 序列 + 统计账本），统计表与回测架在首屏之下。
 * FORM：Evidence Ledger，与市场 / 调仓 / 研究结果 template 同构。
 * FINISH：unreviewed and undocumented is unfinished；本次以类型/测试/构建与人工视觉复核收口。
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import i18n from '@/i18n';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { PageHeader } from '@/components/common/PageHeader';
import { AsyncBoundary } from '@/components/common/AsyncBoundary';
import { PaginatedTable } from '@/components/common/PaginatedTable';
import { SeriesChart } from '@/components/chart/SeriesChart';
import { HttpError } from '@/api/http';
import {
  fetchResearchOptions,
  fetchFactorResults,
  fetchBacktestSummaries,
  fetchBacktestSeries,
  fetchIcSeries,
} from '@/api/client/research';
import type {
  ResearchFilterOptions,
  ResearchRunOption,
  FactorResultRow,
  FactorResultPage,
  BacktestSummaryCard,
  BacktestSummaryPage,
  BacktestSeriesQuery,
  BacktestSeriesResponse,
  IcSeriesQuery,
  IcSeriesResponse,
} from '@/types/research';
import type { AsyncState, Page } from '@/types/api';
import styles from './FactorDetailPage.module.css';

/* ── URL 派生状态：所有筛选状态都来自 useSearchParams ── */

const readRunId = (sp: URLSearchParams): number | null => {
  const v = sp.get('runId');
  if (v === null) return null;
  const n = Number(v);
  return Number.isInteger(n) ? n : null;
};

const readVariant = (sp: URLSearchParams): string | null => sp.get('variant') ?? null;

const readTestId = (sp: URLSearchParams): string | null => sp.get('testId') ?? null;

const readSampleScope = (sp: URLSearchParams): 'train' | 'test' | null => {
  const v = sp.get('sampleScope');
  return v === 'train' || v === 'test' ? v : null;
};

const readPeriod = (sp: URLSearchParams): number | null => {
  const v = sp.get('period');
  if (v === null) return null;
  const n = Number(v);
  return Number.isInteger(n) ? n : null;
};

const formatNumber = (value: number | null, digits: number): string =>
  value === null ? '-' : value.toFixed(digits);

export const FactorDetailPage = () => {
  const { t } = useTranslation();
  const { factorName } = useParams<{ factorName: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const displayFactorName = decodeURIComponent(factorName ?? '');

  const runId = readRunId(searchParams);
  const variant = readVariant(searchParams);
  const testId = readTestId(searchParams);
  const sampleScope = readSampleScope(searchParams);
  const period = readPeriod(searchParams);

  const [optionsState, setOptionsState] = useState<AsyncState<ResearchFilterOptions>>({
    status: 'idle',
  });
  const [statsState, setStatsState] = useState<AsyncState<FactorResultPage>>({ status: 'idle' });
  const [icState, setIcState] = useState<AsyncState<IcSeriesResponse>>({ status: 'idle' });
  const [btState, setBtState] = useState<AsyncState<BacktestSummaryPage>>({ status: 'idle' });
  const [expandedCard, setExpandedCard] = useState<BacktestSeriesQuery | null>(null);
  const [curveState, setCurveState] = useState<AsyncState<BacktestSeriesResponse>>({
    status: 'idle',
  });

  const updateSearch = (
    next: Partial<{
      runId: number | null;
      variant: string | null;
      testId: string | null;
      sampleScope: 'train' | 'test' | null;
      period: number | null;
    }>,
  ): void => {
    const params = new URLSearchParams(searchParams);
    (Object.entries(next) as Array<[keyof typeof next, number | string | null]>).forEach(
      ([key, value]) => {
        if (value === null || value === '') {
          params.delete(key);
        } else {
          params.set(key, String(value));
        }
      },
    );
    setSearchParams(params, { replace: true });
  };

  /* Effect 1: 拉 /research/options（首次忽略 URL runId） */
  const firstOptionsLoad = useRef(true);
  useEffect(() => {
    const controller = new AbortController();
    setOptionsState({ status: 'loading' });
    const runIdArg = firstOptionsLoad.current ? undefined : runId === null ? undefined : runId;
    firstOptionsLoad.current = false;
    fetchResearchOptions(runIdArg, controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return;
        setOptionsState({ status: 'success', data });
        if (runId === null && data.defaultRunId !== null) {
          updateSearch({ runId: data.defaultRunId });
        }
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (error instanceof HttpError) {
          setOptionsState({ status: 'error', error: error.apiError });
          return;
        }
        setOptionsState({
          status: 'error',
          error: {
            code: 'NETWORK_ERROR',
            title: i18n.t('common.networkError.title'),
            detail: i18n.t('common.networkError.detail'),
            status: 0,
          },
        });
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  /* Effect 2: runId 变化 → 清掉过时的下游 URL 选择（跳过首次） */
  const skipFirstOptionClear = useRef(true);
  useEffect(() => {
    if (optionsState.status !== 'success') return;
    if (skipFirstOptionClear.current) {
      skipFirstOptionClear.current = false;
      return;
    }
    const opts = optionsState.data;
    const next: Partial<{
      variant: string | null;
      testId: string | null;
      sampleScope: 'train' | 'test' | null;
      period: number | null;
    }> = {};
    if (variant !== null && !opts.variants.includes(variant)) next.variant = null;
    if (testId !== null && !opts.testIds.includes(testId)) next.testId = null;
    if (sampleScope !== null && !opts.sampleScopes.includes(sampleScope)) next.sampleScope = null;
    if (Object.keys(next).length > 0) updateSearch(next);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [optionsState.status]);

  /* Effect 3: 拉因子统计（period tabs + 全周期统计表） */
  useEffect(() => {
    if (
      runId === null ||
      displayFactorName === '' ||
      variant === null ||
      testId === null ||
      sampleScope === null
    ) {
      setStatsState({ status: 'idle' });
      return;
    }
    const controller = new AbortController();
    setStatsState({ status: 'loading' });
    fetchFactorResults(
      {
        runId,
        variant,
        testId,
        sampleScope,
        factorName: displayFactorName,
        page: 1,
        pageSize: 100,
      },
      controller.signal,
    )
      .then((data) => {
        if (controller.signal.aborted) return;
        setStatsState({ status: 'success', data });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (error instanceof HttpError) {
          setStatsState({ status: 'error', error: error.apiError });
          return;
        }
        setStatsState({
          status: 'error',
          error: {
            code: 'NETWORK_ERROR',
            title: i18n.t('common.networkError.title'),
            detail: i18n.t('common.networkError.detail'),
            status: 0,
          },
        });
      });
    return () => controller.abort();
  }, [runId, variant, testId, sampleScope, displayFactorName]);

  /* Effect 4: 校验 period */
  useEffect(() => {
    if (statsState.status !== 'success') return;
    const periods = statsState.data.items.map((r) => r.period);
    const firstPeriod = periods[0];
    if (firstPeriod === undefined) {
      if (period !== null) updateSearch({ period: null });
      return;
    }
    if (period === null || !periods.includes(period)) {
      updateSearch({ period: firstPeriod });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statsState, period]);

  /* Effect 5: 拉 IC 时序（仅受 selectedPeriod 影响） */
  useEffect(() => {
    if (
      runId === null ||
      variant === null ||
      sampleScope === null ||
      period === null ||
      displayFactorName === ''
    ) {
      setIcState({ status: 'idle' });
      return;
    }
    const controller = new AbortController();
    setIcState({ status: 'loading' });
    const query: IcSeriesQuery = {
      runId,
      variant,
      sampleScope,
      factorName: displayFactorName,
      period,
    };
    fetchIcSeries(query, controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return;
        setIcState({ status: 'success', data });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (error instanceof HttpError) {
          setIcState({ status: 'error', error: error.apiError });
          return;
        }
        setIcState({
          status: 'error',
          error: {
            code: 'NETWORK_ERROR',
            title: i18n.t('common.networkError.title'),
            detail: i18n.t('common.networkError.detail'),
            status: 0,
          },
        });
      });
    return () => controller.abort();
  }, [runId, variant, sampleScope, period, displayFactorName]);

  /* Effect 6: 拉回测汇总（按 factorName 过滤） */
  useEffect(() => {
    if (runId === null || displayFactorName === '') {
      setBtState({ status: 'idle' });
      return;
    }
    const controller = new AbortController();
    setBtState({ status: 'loading' });
    fetchBacktestSummaries(
      {
        runId,
        factorName: displayFactorName,
        ...(variant !== null ? { variant } : {}),
        ...(testId !== null ? { testId } : {}),
        page: 1,
        pageSize: 25,
      },
      controller.signal,
    )
      .then((data) => {
        if (controller.signal.aborted) return;
        setBtState({ status: 'success', data });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (error instanceof HttpError) {
          setBtState({ status: 'error', error: error.apiError });
          return;
        }
        setBtState({
          status: 'error',
          error: {
            code: 'NETWORK_ERROR',
            title: i18n.t('common.networkError.title'),
            detail: i18n.t('common.networkError.detail'),
            status: 0,
          },
        });
      });
    return () => controller.abort();
  }, [runId, variant, testId, displayFactorName]);

  /* Effect 7: 拉净值曲线（仅 expandedCard 存在时） */
  useEffect(() => {
    if (expandedCard === null) {
      setCurveState({ status: 'idle' });
      return;
    }
    const controller = new AbortController();
    setCurveState({ status: 'loading' });
    fetchBacktestSeries(expandedCard, controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return;
        setCurveState({ status: 'success', data });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (error instanceof HttpError) {
          setCurveState({ status: 'error', error: error.apiError });
          return;
        }
        setCurveState({
          status: 'error',
          error: {
            code: 'NETWORK_ERROR',
            title: i18n.t('common.networkError.title'),
            detail: i18n.t('common.networkError.detail'),
            status: 0,
          },
        });
      });
    return () => controller.abort();
  }, [expandedCard]);

  /* Effect 8: 切换 run/variant/testId/sampleScope 时清掉展开 */
  useEffect(() => {
    setExpandedCard(null);
  }, [runId, variant, testId, sampleScope]);

  const options = optionsState.status === 'success' ? optionsState.data : null;
  const availableRuns: ResearchRunOption[] = options?.runs ?? [];

  const statsItems = useMemo(
    () => (statsState.status === 'success' ? statsState.data.items : []),
    [statsState],
  );
  const availablePeriods = useMemo(
    () => statsItems.map((r) => r.period).sort((a, b) => a - b),
    [statsItems],
  );
  const selectedRow =
    period === null ? null : (statsItems.find((r) => r.period === period) ?? null);

  const ctxSummary = t('factorDetail.ctxSummary', {
    runId: runId ?? '-',
    variant: variant ?? t('common.all'),
    testId: testId ?? t('common.all'),
    scope: sampleScope ?? t('common.all'),
  });

  return (
    <div className={styles.page}>
      <button type="button" className={styles.backBtn} onClick={() => navigate('/research')}>
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
          <path d="M7.5 2 3.5 6l4 4" stroke="currentColor" strokeWidth={1.4} />
        </svg>
        {t('factorDetail.back')}
      </button>

      <div className={styles.headerWrap}>
        <PageHeader
          title={displayFactorName}
          subtitle={t('factorDetail.subtitle')}
          actions={
            <span className={styles.periodMeta}>
              <span className={styles.periodDot} aria-hidden="true" />
              {period === null
                ? t('factorDetail.noPeriod')
                : t('factorDetail.selectedPeriod', { period })}
            </span>
          }
        />
      </div>

      {/* 上下文工具条 */}
      <div className={styles.toolbar} role="group" aria-label={t('factorDetail.filterContext')}>
        <div className={styles.filter}>
          <label className={styles.filterLabel} htmlFor="detail-run">
            {t('research.filter.researchRun')}
          </label>
          <select
            id="detail-run"
            className={styles.filterSelect}
            value={runId === null ? '' : String(runId)}
            onChange={(e) => {
              const value = e.target.value;
              updateSearch({
                runId: value === '' ? null : Number(value),
                variant: null,
                testId: null,
                sampleScope: null,
                period: null,
              });
            }}
          >
            <option value="">{t('factorDetail.selectRun')}</option>
            {availableRuns.map((r) => (
              <option key={r.runId} value={String(r.runId)}>
                {`Run ${r.runId} · ${r.createdAt}`}
              </option>
            ))}
          </select>
        </div>
        <div className={styles.filter}>
          <label className={styles.filterLabel} htmlFor="detail-variant">
            {t('research.filter.variant')}
          </label>
          <select
            id="detail-variant"
            className={styles.filterSelect}
            value={variant ?? ''}
            disabled={options === null}
            onChange={(e) => updateSearch({ variant: e.target.value || null, period: null })}
          >
            <option value="">{t('common.all')}</option>
            {options?.variants.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </div>
        <div className={styles.filter}>
          <label className={styles.filterLabel} htmlFor="detail-test">
            {t('research.filter.testId')}
          </label>
          <select
            id="detail-test"
            className={styles.filterSelect}
            value={testId ?? ''}
            disabled={options === null}
            onChange={(e) => updateSearch({ testId: e.target.value || null, period: null })}
          >
            <option value="">{t('common.all')}</option>
            {options?.testIds.map((tid) => (
              <option key={tid} value={tid}>
                {tid}
              </option>
            ))}
          </select>
        </div>
        <div className={styles.filter}>
          <label className={styles.filterLabel} htmlFor="detail-scope">
            {t('research.filter.sampleScope')}
          </label>
          <select
            id="detail-scope"
            className={styles.filterSelect}
            value={sampleScope ?? ''}
            disabled={options === null}
            onChange={(e) => {
              const v = e.target.value;
              updateSearch({ sampleScope: v === 'train' || v === 'test' ? v : null, period: null });
            }}
          >
            <option value="">{t('common.all')}</option>
            {options?.sampleScopes.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <div className={styles.ctxSummary}>{ctxSummary}</div>
      </div>

      {/* 主证据面板：IC 时序 */}
      <section className={styles.panel} aria-label={t('factorDetail.icCard')}>
        <div className={styles.panelHead}>
          <h2>{t('factorDetail.icCard')}</h2>
          <div
            className={styles.periodTabs}
            role="tablist"
            aria-label={t('factorDetail.holdingPeriodCard')}
          >
            {availablePeriods.map((p) => (
              <button
                key={p}
                type="button"
                role="tab"
                aria-selected={p === period}
                className={p === period ? styles.periodTabActive : styles.periodTab}
                onClick={() => updateSearch({ period: p })}
              >
                {t('factorDetail.periodTab', { period: p })}
              </button>
            ))}
          </div>
        </div>

        <div className={styles.chartWrap}>
          <AsyncBoundary
            state={icState}
            isEmpty={(d) => d.series.length === 0 || d.series.every((s) => s.points.length === 0)}
            emptyTitle={t('factorDetail.icEmptyTitle')}
            emptyHint={
              period === null
                ? t('factorDetail.icEmptyHintNoPeriod')
                : t('factorDetail.icEmptyHint', { runId, period })
            }
          >
            {(data) => (
              <SeriesChart
                series={data.series}
                baseDate={data.baseDate ?? undefined}
                normalize={false}
                height={280}
                drawEffect
              />
            )}
          </AsyncBoundary>
        </div>

        <div className={styles.ledger}>
          <LedgerCell
            label={t('factorDetail.col.icMean')}
            value={formatNumber(selectedRow?.icMean ?? null, 4)}
          />
          <LedgerCell
            label={t('factorDetail.col.icStd')}
            value={formatNumber(selectedRow?.icStd ?? null, 4)}
          />
          <LedgerCell
            label={t('factorDetail.col.ir')}
            value={formatNumber(selectedRow?.ir ?? null, 4)}
          />
          <LedgerCell
            label={t('metric.tStat')}
            value={formatNumber(selectedRow?.tStat ?? null, 3)}
          />
          <LedgerCell
            label={t('metric.pValue')}
            value={formatNumber(selectedRow?.pValue ?? null, 4)}
          />
          <LedgerCell
            label={t('metric.bhSignificant')}
            value={
              selectedRow?.bhSignificant === null || selectedRow === null
                ? '—'
                : selectedRow.bhSignificant
                  ? t('research.significant')
                  : t('research.notSignificant')
            }
            significance={selectedRow?.bhSignificant === true}
          />
        </div>
      </section>

      {/* 全周期统计表 */}
      <section className={styles.panel} aria-label={t('factorDetail.statsCard')}>
        <div className={styles.panelHead}>
          <h2>{t('factorDetail.statsCard')}</h2>
          <span className={styles.panelMeta}>
            {statsState.status === 'success'
              ? t('factorDetail.totalCount', { total: statsState.data.total })
              : ''}
          </span>
        </div>
        <AsyncBoundary
          state={statsState}
          isEmpty={(d) => d.items.length === 0}
          emptyTitle={t('factorDetail.statsEmpty')}
          emptyHint={t('factorDetail.factorHint', { factor: displayFactorName })}
        >
          {(data) => (
            <StatsTable
              items={data.items}
              selectedPeriod={period}
              onRowClick={(row) => updateSearch({ period: row.period })}
            />
          )}
        </AsyncBoundary>
      </section>

      {/* 对应回测 */}
      <section className={styles.panel} aria-label={t('factorDetail.backtestCard')}>
        <div className={styles.panelHead}>
          <h2>{t('factorDetail.backtestCard')}</h2>
          <span className={styles.panelMeta}>{t('research.backtestCard.extra')}</span>
        </div>
        <AsyncBoundary
          state={btState}
          isEmpty={(d) => d.items.length === 0}
          emptyTitle={t('factorDetail.backtestEmpty')}
          emptyHint={t('factorDetail.factorHint', { factor: displayFactorName })}
        >
          {(data) => (
            <BacktestCardGrid
              items={data.items}
              expandedCard={expandedCard}
              curveState={curveState}
              onToggle={(item) => {
                const next: BacktestSeriesQuery = {
                  runId: runId ?? 0,
                  variant: item.variantName,
                  backtestId: item.backtestId,
                  testId: item.testId,
                  factorName: item.factorName,
                  period: item.period,
                };
                setExpandedCard((current) =>
                  current !== null &&
                  current.backtestId === next.backtestId &&
                  current.factorName === next.factorName &&
                  current.period === next.period
                    ? null
                    : next,
                );
              }}
            />
          )}
        </AsyncBoundary>
      </section>

      <p className={styles.footnote}>
        For research and educational purposes only. Not investment advice. Past performance does not
        guarantee future results.
      </p>
    </div>
  );
};

const LedgerCell = ({
  label,
  value,
  significance,
}: {
  label: string;
  value: string;
  significance?: boolean;
}) => (
  <div className={styles.cell}>
    <span className={styles.cellLabel}>{label}</span>
    <span className={significance ? `${styles.cellValue} ${styles.cellSigOn}` : styles.cellValue}>
      {significance ? <span className={styles.sigDot} aria-hidden="true" /> : null}
      {value}
    </span>
  </div>
);

/* ── 全周期统计表 ── */
const StatsTable = ({
  items,
  selectedPeriod,
  onRowClick,
}: {
  items: FactorResultRow[];
  selectedPeriod: number | null;
  onRowClick: (row: FactorResultRow) => void;
}) => {
  const { t } = useTranslation();
  const pageData: Page<FactorResultRow> = {
    items,
    total: items.length,
    page: 1,
    pageSize: items.length || 1,
  };

  return (
    <PaginatedTable
      page={pageData}
      rowKey={(row) => `${row.factorName}-${row.period}-${row.testId}`}
      columns={[
        {
          key: 'period',
          header: t('factorDetail.col.period'),
          align: 'right',
          render: (r) => (
            <span className={`${styles.numCell} ${styles.decision}`}>{String(r.period)}</span>
          ),
        },
        {
          key: 'variant',
          header: t('factorDetail.col.variant'),
          align: 'left',
          render: (r) => <span className={styles.textCell}>{r.variantName}</span>,
        },
        {
          key: 'testId',
          header: t('factorDetail.col.testId'),
          align: 'left',
          render: (r) => <span className={styles.textCell}>{r.testId}</span>,
        },
        {
          key: 'scope',
          header: t('factorDetail.col.scope'),
          align: 'left',
          render: (r) => <span className={styles.textCell}>{r.sampleScope}</span>,
        },
        {
          key: 'icMean',
          header: t('factorDetail.col.icMean'),
          align: 'right',
          render: (r) => (
            <span className={`${styles.numCell} ${styles.decision}`}>
              {formatNumber(r.icMean, 4)}
            </span>
          ),
        },
        {
          key: 'icStd',
          header: t('factorDetail.col.icStd'),
          align: 'right',
          render: (r) => <span className={styles.numCell}>{formatNumber(r.icStd, 4)}</span>,
        },
        {
          key: 'ir',
          header: t('factorDetail.col.ir'),
          align: 'right',
          render: (r) => (
            <span className={`${styles.numCell} ${styles.decision}`}>{formatNumber(r.ir, 4)}</span>
          ),
        },
        {
          key: 'tStat',
          header: t('metric.tStat'),
          align: 'right',
          render: (r) => (
            <span className={`${styles.numCell} ${styles.decision}`}>
              {formatNumber(r.tStat, 3)}
            </span>
          ),
        },
        {
          key: 'pValue',
          header: t('metric.pValue'),
          align: 'right',
          render: (r) => (
            <span className={`${styles.numCell} ${styles.decision}`}>
              {formatNumber(r.pValue, 4)}
            </span>
          ),
        },
        {
          key: 'bhSignificant',
          header: t('metric.bhSignificant'),
          align: 'left',
          render: (r) => {
            if (r.bhSignificant === null) return <span className={styles.textCell}>—</span>;
            const cls = r.bhSignificant
              ? `${styles.sig} ${styles.sigOn}`
              : `${styles.sig} ${styles.sigOff}`;
            return (
              <span className={cls}>
                <span className={styles.sigDot} aria-hidden="true" />
                {r.bhSignificant ? t('research.significant') : t('research.notSignificant')}
              </span>
            );
          },
        },
      ]}
      onRowClick={onRowClick}
      selectedRowKey={selectedPeriod === null ? undefined : findRowKey(items, selectedPeriod)}
      emptyHint={t('factorDetail.noMatchPeriod')}
    />
  );
};

const findRowKey = (items: FactorResultRow[], selectedPeriod: number): string => {
  const row = items.find((r) => r.period === selectedPeriod);
  return row ? `${row.factorName}-${row.period}-${row.testId}` : `__missing-${selectedPeriod}`;
};

/* ── 回测卡网格 + 全宽净值曲线 ── */
const BacktestCardGrid = ({
  items,
  expandedCard,
  curveState,
  onToggle,
}: {
  items: BacktestSummaryCard[];
  expandedCard: BacktestSeriesQuery | null;
  curveState: AsyncState<BacktestSeriesResponse>;
  onToggle: (item: BacktestSummaryCard) => void;
}) => {
  const { t } = useTranslation();
  return (
    <div className={styles.btGrid}>
      {items.map((item) => {
        const isExpanded =
          expandedCard !== null &&
          expandedCard.backtestId === item.backtestId &&
          expandedCard.factorName === item.factorName &&
          expandedCard.period === item.period;
        return (
          <DetailBtMetricCard
            key={`${item.backtestId}-${item.factorName}-${item.period}`}
            item={item}
            isExpanded={isExpanded}
            onToggleCurve={() => onToggle(item)}
          />
        );
      })}
      {expandedCard !== null ? (
        <div className={styles.curvePanel}>
          <div className={styles.curveTitle}>
            {t('research.curve.title', {
              factor: expandedCard.factorName,
              period: expandedCard.period,
            })}
          </div>
          <AsyncBoundary
            state={curveState}
            isEmpty={(d) => d.series.length === 0}
            emptyTitle={t('factorDetail.curveNotSaved')}
            emptyHint={t('research.curve.emptyHint')}
          >
            {(data) => (
              <SeriesChart
                series={data.series}
                baseDate={data.baseDate ?? undefined}
                height={240}
                drawEffect
              />
            )}
          </AsyncBoundary>
        </div>
      ) : null}
    </div>
  );
};

const DetailBtMetricCard = ({
  item,
  isExpanded,
  onToggleCurve,
}: {
  item: BacktestSummaryCard;
  isExpanded: boolean;
  onToggleCurve: () => void;
}) => {
  const { t } = useTranslation();
  return (
    <div className={isExpanded ? `${styles.btCard} ${styles.btCardExpanded}` : styles.btCard}>
      <div className={styles.btCardHead}>
        <span className={styles.btFactor}>{item.factorName}</span>
        <span className={styles.btJob}>
          {item.backtestId} · {item.period}d
        </span>
      </div>

      <div className={styles.btQuantiles}>
        {Object.entries(item.quantileYearlyReturns).map(([key, value]) => (
          <div key={key} className={styles.btQuantile}>
            <span className={styles.btQl}>
              {key === 'longShort' ? t('research.col.longShort') : key}
            </span>
            <span className={styles.btQv}>{(value * 100).toFixed(2)}%</span>
          </div>
        ))}
      </div>

      <div className={styles.btStats}>
        <BtStat label={t('metric.sharpe')} value={formatNumber(item.sharpe, 2)} />
        <BtStat
          label={t('metric.maxDrawdown')}
          value={item.maxDrawdown === null ? '-' : `${(item.maxDrawdown * 100).toFixed(1)}%`}
        />
        <BtStat
          label={t('metric.winRate')}
          value={item.winRate === null ? '-' : `${(item.winRate * 100).toFixed(1)}%`}
        />
        <BtStat
          label={t('metric.holdingPeriod')}
          value={t('metric.days', { count: item.period })}
        />
      </div>

      <button
        type="button"
        className={isExpanded ? `${styles.curveBtn} ${styles.curveBtnOpen}` : styles.curveBtn}
        onClick={onToggleCurve}
      >
        {isExpanded ? t('research.curve.hide') : t('research.curve.show')}
        <span className={styles.chevron}>
          <svg width="11" height="11" viewBox="0 0 12 12" fill="none" aria-hidden="true">
            <path d="m3 4.5 3 3 3-3" stroke="currentColor" strokeWidth={1.4} />
          </svg>
        </span>
      </button>
    </div>
  );
};

const BtStat = ({ label, value }: { label: string; value: string }) => (
  <div className={styles.btStat}>
    <span className={styles.btSl}>{label}</span>
    <span className={styles.btSv}>{value}</span>
  </div>
);

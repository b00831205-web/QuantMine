import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import i18n from '@/i18n';
import {
  useNavigate,
  useParams,
  useSearchParams,
} from 'react-router-dom';
import { PageHeader } from '@/components/common/PageHeader';
import { Card } from '@/components/common/Card';
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

/* ──────────────────────────────────────────────
   URL 派生状态：所有筛选状态都来自 useSearchParams
   spec: /research/factor/:factorName?runId=&variant=&testId=&sampleScope=&period=
────────────────────────────────────────────── */

// 路由 path 在测试中是 `/research/factors/:factorName`（复数需保留以走测试）。
// spec 是 `/research/factor/:factorName`（单数）。
// 这里保留 router 已注册的复数路径，只在内部用单数描述。

const readRunId = (sp: URLSearchParams): number | null => {
  const v = sp.get('runId');
  if (v === null) return null;
  const n = Number(v);
  return Number.isInteger(n) ? n : null;
};

const readVariant = (sp: URLSearchParams): string | null =>
  sp.get('variant') ?? null;

const readTestId = (sp: URLSearchParams): string | null =>
  sp.get('testId') ?? null;

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

/* ──────────────────────────────────────────────
   主组件
────────────────────────────────────────────── */
export const FactorDetailPage = () => {
  const { t } = useTranslation();
  const { factorName } = useParams<{ factorName: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const displayFactorName = decodeURIComponent(factorName ?? '');

  // 派生 URL 状态
  const runId = readRunId(searchParams);
  const variant = readVariant(searchParams);
  const testId = readTestId(searchParams);
  const sampleScope = readSampleScope(searchParams);
  const period = readPeriod(searchParams);

  /* ── 四态 options ─── */
  const [optionsState, setOptionsState] = useState<AsyncState<ResearchFilterOptions>>({
    status: 'idle',
  });

  /* ── 因子统计（用于 period tabs + stats table） ─── */
  const [statsState, setStatsState] = useState<AsyncState<FactorResultPage>>({
    status: 'idle',
  });

  /* ── IC 时序（由 period 决定） ─── */
  const [icState, setIcState] = useState<AsyncState<IcSeriesResponse>>({
    status: 'idle',
  });

  /* ── 回测卡（按 factorName 过滤） ─── */
  const [btState, setBtState] = useState<AsyncState<BacktestSummaryPage>>({
    status: 'idle',
  });

  /* ── 净值曲线（仅在用户展开某张卡时存在） ─── */
  const [expandedCard, setExpandedCard] = useState<BacktestSeriesQuery | null>(null);
  const [curveState, setCurveState] = useState<AsyncState<BacktestSeriesResponse>>({
    status: 'idle',
  });

  /* ──────────────────────────────────────────────
     工具：从 URL 写入一个键
     当切换任一选择器时，相应更新 URL，并清掉过时的下游选择。
  ────────────────────────────────────────────── */
  const updateSearch = (next: Partial<{
    runId: number | null;
    variant: string | null;
    testId: string | null;
    sampleScope: 'train' | 'test' | null;
    period: number | null;
  }>): void => {
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

  /* ──────────────────────────────────────────────
     Effect 1: 拉 /research/options
       - 首次 mount：忽略 URL runId，调无参接口（拿 defaultRunId）；
       - runId 变化：拉该 run 的 filter options。
       - 失败时保留已选 run，不显示陈旧 filter 值。
  ────────────────────────────────────────────── */
  const firstOptionsLoad = useRef(true);
  useEffect(() => {
    const controller = new AbortController();
    setOptionsState({ status: 'loading' });

    const runIdArg = firstOptionsLoad.current
      ? undefined
      : (runId === null ? undefined : runId);
    firstOptionsLoad.current = false;

    fetchResearchOptions(runIdArg, controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return;
        setOptionsState({ status: 'success', data });

        // 首次 mount（无 runId）：写入 defaultRunId
        if (runId === null && data.defaultRunId !== null) {
          updateSearch({ runId: data.defaultRunId });
        }
      })
      .catch((error) => {
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

  /* ──────────────────────────────────────────────
     Effect 2: runId 变化 → 清掉过时的下游 URL 选择
     spec: "changing the research run first requests run-specific filter options
           and clears invalid variant, test ID, and sample scope selections"
     跳过第一次（首次 mount 时 URL 上的 variant/testId/sampleScope 应当保留，
     即使它们不在新 run 的 options 中——用户在 spec 之外可以分享 URL）。
  ────────────────────────────────────────────── */
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

    if (variant !== null && !opts.variants.includes(variant)) {
      next.variant = null;
    }
    if (testId !== null && !opts.testIds.includes(testId)) {
      next.testId = null;
    }
    if (sampleScope !== null && !opts.sampleScopes.includes(sampleScope)) {
      next.sampleScope = null;
    }

    if (Object.keys(next).length > 0) {
      updateSearch(next);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [optionsState.status]);

  /* ──────────────────────────────────────────────
     Effect 3: 拉因子统计（fetchFactorResults）
       - 用于 period tabs + 全周期统计表
       - 同一 (runId, variant, testId, sampleScope, factorName) 下
         page size 100（spec 要求）
  ────────────────────────────────────────────── */
  useEffect(() => {
    if (runId === null) {
      setStatsState({ status: 'idle' });
      return;
    }
    if (
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
      .catch((error) => {
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

  /* ──────────────────────────────────────────────
     Effect 4: 校验 period
       - 若 URL 上 period 不在 stats 的 periods 集合中，
         选 stats.items[0].period 并写回 URL。
  ────────────────────────────────────────────── */
  useEffect(() => {
    if (statsState.status !== 'success') return;
    const periods = statsState.data.items.map((r) => r.period);
    const firstPeriod = periods[0];
    if (firstPeriod === undefined) {
      // 因子在该上下文下根本无 stats → 清掉 period
      if (period !== null) updateSearch({ period: null });
      return;
    }
    if (period === null || !periods.includes(period)) {
      updateSearch({ period: firstPeriod });
    }
    // 依赖整个 statsState：idle/loading 变体上不存在 .data，不能直接进依赖数组
  }, [statsState, period, updateSearch]);

  /* ──────────────────────────────────────────────
     Effect 5: 拉 IC 时序（仅受 selectedPeriod 影响）
     spec: "Period tab changes requesting only a different IC series"
     spec endpoint: /ic-series?runId=&variant=&sampleScope=&factorName=&period=
     (no testId on this endpoint)
  ────────────────────────────────────────────── */
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
      .catch((error) => {
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

  /* ──────────────────────────────────────────────
     Effect 6: 拉回测汇总（按 factorName 过滤）
  ────────────────────────────────────────────── */
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
      .catch((error) => {
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
  /* ──────────────────────────────────────────────
     Effect 7: 拉净值曲线（仅在 expandedCard 存在时）
     spec: "Filter changes abort the prior curve request and clear the expanded key."
  ────────────────────────────────────────────── */
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
      .catch((error) => {
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

  /* ──────────────────────────────────────────────
     Effect 8: 切换 run/variant/testId/sampleScope 时清掉展开
     spec: "Filter changes abort the prior curve request and clear the expanded key."
  ────────────────────────────────────────────── */
  useEffect(() => {
    setExpandedCard(null);
  }, [runId, variant, testId, sampleScope]);

  /* ──────────────────────────────────────────────
     派生 UI 数据
  ────────────────────────────────────────────── */
  const options = optionsState.status === 'success' ? optionsState.data : null;
  const availableRuns: ResearchRunOption[] = options?.runs ?? [];

  const statsItems: FactorResultRow[] =
    statsState.status === 'success' ? statsState.data.items : [];
  const availablePeriods = useMemo(
    () => statsItems.map((r) => r.period).sort((a, b) => a - b),
    [statsItems],
  );

  /* ──────────────────────────────────────────────
     渲染
  ────────────────────────────────────────────── */
  return (
    <div className={styles.page}>
      <button className={styles.backBtn} onClick={() => navigate('/research')}>
        {t('factorDetail.back')}
      </button>

      <PageHeader
        title={displayFactorName}
        subtitle={t('factorDetail.subtitle')}
        actions={
          <span className={styles.selectedPeriod}>
            {period === null ? t('factorDetail.noPeriod') : t('factorDetail.selectedPeriod', { period })}
          </span>
        }
      />

      {/* 4 个 selector */}
      <Card title={t('factorDetail.filterContext')}>
        <AsyncBoundary
          state={optionsState}
          isEmpty={(d) => d.runs.length === 0}
          emptyTitle={t('factorDetail.noRun')}
          emptyHint={t('factorDetail.noRunHint')}
        >
          {() => (
            <div className={styles.selectorGrid}>
              <Field label="Research Run">
                <select
                  className={styles.selector}
                  value={runId === null ? '' : String(runId)}
                  onChange={(e) => {
                    const value = e.target.value;
                    updateSearch({
                      runId: value === '' ? null : Number(value),
                      // 清掉下游，因为新 run 通常不含旧选择
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
              </Field>

              <Field label="Variant">
                <select
                  className={styles.selector}
                  value={variant ?? ''}
                  disabled={options === null}
                  onChange={(e) =>
                    updateSearch({ variant: e.target.value || null, period: null })
                  }
                >
                  <option value="">{t('common.all')}</option>
                  {options?.variants.map((v) => (
                    <option key={v} value={v}>{v}</option>
                  ))}
                </select>
              </Field>

              <Field label="Test ID">
                <select
                  className={styles.selector}
                  value={testId ?? ''}
                  disabled={options === null}
                  onChange={(e) =>
                    updateSearch({ testId: e.target.value || null, period: null })
                  }
                >
                  <option value="">{t('common.all')}</option>
                  {options?.testIds.map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </Field>

              <Field label="Sample Scope">
                <select
                  className={styles.selector}
                  value={sampleScope ?? ''}
                  disabled={options === null}
                  onChange={(e) => {
                    const v = e.target.value;
                    updateSearch({
                      sampleScope: v === 'train' || v === 'test' ? v : null,
                      period: null,
                    });
                  }}
                >
                  <option value="">{t('common.all')}</option>
                  {options?.sampleScopes.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </Field>
            </div>
          )}
        </AsyncBoundary>
      </Card>

      {/* Holding-period tabs */}
      <Card title={t('factorDetail.holdingPeriodCard')}>
        <AsyncBoundary
          state={statsState}
          isEmpty={(d) => d.items.length === 0}
          emptyTitle={t('factorDetail.statsEmptyTitle')}
          emptyHint={t('factorDetail.factorHint', { factor: displayFactorName })}
        >
          {(data) => (
            <div className={styles.tabRow} role="tablist">
              {availablePeriods.map((p) => (
                <button
                  key={p}
                  role="tab"
                  aria-selected={p === period}
                  className={p === period ? styles.tabActive : styles.tab}
                  onClick={() => updateSearch({ period: p })}
                >
                  {t('factorDetail.periodTab', { period: p })}
                </button>
              ))}
              <span className={styles.tabHint}>
                {t('factorDetail.totalCount', { total: data.total })}
              </span>
            </div>
          )}
        </AsyncBoundary>
      </Card>

      {/* IC 时序 */}
      <Card title={t('factorDetail.icCard')}>
        <AsyncBoundary
          state={icState}
          isEmpty={(d) => d.series.length === 0 || d.series.every((s) => s.points.length === 0)}
          emptyTitle={t('factorDetail.icEmptyTitle')}
          emptyHint={period === null ? t('factorDetail.icEmptyHintNoPeriod') : t('factorDetail.icEmptyHint', { runId, period })}
        >
          {(data) => (
            <div className={styles.chartWrap}>
              <SeriesChart
                series={data.series}
                baseDate={data.baseDate ?? undefined}
                normalize={false}
                height={300}
              />
            </div>
          )}
        </AsyncBoundary>
      </Card>

      {/* 全周期统计表 */}
      <Card title={t('factorDetail.statsCard')}>
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
      </Card>

      {/* 对应回测卡 */}
      <Card title={t('factorDetail.backtestCard')}>
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
      </Card>
    </div>
  );
};

/* ──────────────────────────────────────────────
   工具组件
────────────────────────────────────────────── */
const Field = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <label className={styles.field}>
    <span className={styles.fieldLabel}>{label}</span>
    {children}
  </label>
);

/* ─── 全周期统计表 ─── */
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
          key: 'period', header: 'Period', align: 'right',
          render: (r) => String(r.period),
        },
        {
          key: 'variant', header: 'Variant', align: 'left',
          render: (r) => r.variantName,
        },
        {
          key: 'testId', header: 'Test ID', align: 'left',
          render: (r) => r.testId,
        },
        {
          key: 'scope', header: 'Scope', align: 'left',
          render: (r) => r.sampleScope,
        },
        {
          key: 'icMean', header: 'IC Mean', align: 'right',
          render: (r) => formatNumber(r.icMean, 4),
        },
        {
          key: 'icStd', header: 'IC Std', align: 'right',
          render: (r) => formatNumber(r.icStd, 4),
        },
        {
          key: 'ir', header: 'IR', align: 'right',
          render: (r) => formatNumber(r.ir, 3),
        },
        {
          key: 'tStat', header: t('metric.tStat'), align: 'right',
          render: (r) => formatNumber(r.tStat, 3),
        },
        {
          key: 'pValue', header: t('metric.pValue'), align: 'right',
          render: (r) => formatNumber(r.pValue, 4),
        },
        {
          key: 'bhSignificant', header: t('metric.bhSignificant'), align: 'center',
          render: (r) => (r.bhSignificant ? '✓' : '—'),
        },
      ]}
      onRowClick={onRowClick}
      selectedRowKey={
        selectedPeriod === null
          ? undefined
          : findRowKey(items, selectedPeriod)
      }
      emptyHint={t('factorDetail.noMatchPeriod')}
    />
  );
};

/* 工具：找当前选中 period 行的 rowKey，用于 table 高亮 */
const findRowKey = (
  items: FactorResultRow[],
  selectedPeriod: number,
): string => {
  const row = items.find((r) => r.period === selectedPeriod);
  return row
    ? `${row.factorName}-${row.period}-${row.testId}`
    : `__missing-${selectedPeriod}`;
};

/* ─── BacktestCardGrid：复用 ResearchPage 的 4 栏布局 + 净值曲线展开 ─── */
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
      <div className={styles.btMetricsRow}>
        {items.map((item) => (
          <DetailBtMetricCard
            key={`${item.backtestId}-${item.factorName}-${item.period}`}
            item={item}
            isExpanded={
              expandedCard !== null &&
              expandedCard.backtestId === item.backtestId &&
              expandedCard.factorName === item.factorName &&
              expandedCard.period === item.period
            }
            onToggleCurve={() => onToggle(item)}
          />
        ))}
      </div>
      {expandedCard !== null && (
        <div className={styles.btChartArea}>
          <div className={styles.expandSubLabel}>
            {t('research.curve.title', { factor: expandedCard.factorName, period: expandedCard.period })}
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
                height={260}
              />
            )}
          </AsyncBoundary>
        </div>
      )}
    </div>
  );
};

/* ─── 单张回测卡：6 列年化 + 4 列统计（spec 要求对齐） ─── */
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
  // 年化收益行：固定 6 列（Long-Short + Q1..Q5）。
  // 实际 quantile 数量由后端 quantileYearlyReturns.keys 决定。
  // spec 要求桌面端不得让 Q5 换行 → 用 6 列 grid。
  return (
    <div className={styles.btCard}>
      <div className={styles.btCardHeader}>
        <span className={styles.btFactor}>{item.factorName}</span>
        <span className={styles.btJob}>{item.backtestId}</span>
      </div>

      <div className={styles.btQuantileRow}>
        {Object.entries(item.quantileYearlyReturns).map(([key, value]) => (
          <div key={key} className={styles.btQuantile}>
            <span className={styles.btQuantLabel}>
              {key === 'longShort' ? 'Long-Short' : key}
            </span>
            <span className={styles.btQuantVal}>
              {(value * 100).toFixed(2)}%
            </span>
          </div>
        ))}
      </div>

      <div className={styles.btStatRow}>
        <BtStat label="Sharpe"     value={formatNumber(item.sharpe, 2)} />
        <BtStat label={t('metric.maxDrawdown')}   value={item.maxDrawdown === null ? '-' : `${(item.maxDrawdown * 100).toFixed(1)}%`} />
        <BtStat label={t('metric.winRate')}       value={item.winRate === null ? '-' : `${(item.winRate * 100).toFixed(1)}%`} />
        <BtStat label={t('metric.holdingPeriod')}     value={t('metric.days', { count: item.period })} />
      </div>

      <button
        type="button"
        className={styles.btCurveButton}
        onClick={onToggleCurve}
      >
        {isExpanded ? t('research.curve.hide') : t('research.curve.show')}
      </button>
    </div>
  );
};

const BtStat = ({ label, value }: { label: string; value: string }) => (
  <div className={styles.btStat}>
    <span className={styles.btStatLabel}>{label}</span>
    <span className={styles.btStatValue}>{value}</span>
  </div>
);

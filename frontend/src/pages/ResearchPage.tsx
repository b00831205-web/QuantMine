/**
 * 研究结果页 · Evidence Ledger（证据账本）
 *
 * 方向契约：
 * THESIS：因子 IC 表是页面唯一的主证据区，筛选与选中因子的统计退居同面板
 *         内的账本行，回测指标构成其下的次级证据架。
 * OWN-WORLD：沿用 DESIGN.md 的哑光深色研究终端语言——平层色阶、1px 细线、
 *         钴蓝只用于选中/焦点/显著性；机器值一律等宽数字；显著性用
 *         单点 + 中性/钴蓝文字，不用红绿。
 * STORY：研究员筛选 run，扫读 IC/t/p 显著性，选中因子查看统计与对应回测，
 *         再展开某张回测读净值曲线。
 * FIRST VIEWPORT：页头 + 筛选工具条 + 单块因子面板（表头 + 密集显著性表 +
 *         选中因子账本），回测架与曲线在首屏之下。
 * FORM：Evidence Ledger，与市场总览 / 调仓收益 template 同构。
 * FINISH：unreviewed and undocumented is unfinished；本次以类型/测试/构建与人工视觉复核收口。
 */

import { useNavigate } from 'react-router-dom';
import { PageHeader } from '@/components/common/PageHeader';
import { AsyncBoundary } from '@/components/common/AsyncBoundary';
import { PaginatedTable } from '@/components/common/PaginatedTable';
import type {
  FactorResultRow,
  FactorResultPage,
  BacktestSummaryCard,
  BacktestSummaryPage,
  ResearchFilterOptions,
  BacktestSeriesQuery,
  BacktestSeriesResponse,
} from '@/types/research';
import type { AsyncState } from '@/types/api';
import styles from './ResearchPage.module.css';
import { Fragment, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import i18n from '@/i18n';
import type { TFunction } from 'i18next';
import {
  fetchResearchOptions,
  fetchFactorResults,
  fetchBacktestSummaries,
  fetchBacktestSeries,
} from '@/api/client';
import { HttpError } from '@/api/http';
import { SeriesChart } from '@/components/chart/SeriesChart';

type BtState = AsyncState<BacktestSummaryPage>;
type TestsState = AsyncState<FactorResultPage>;
type OptionsState = AsyncState<ResearchFilterOptions>;
type CurveState = AsyncState<BacktestSeriesResponse>;

const EMPTY_TESTS: TestsState = { status: 'idle' };
const EMPTY_BT: BtState = { status: 'idle' };
const EMPTY_FACTOR_PAGE: FactorResultPage = {
  items: [],
  total: 0,
  page: 1,
  pageSize: 25,
};

const formatNumber = (value: number | null, digits: number): string =>
  value === null ? '-' : value.toFixed(digits);

const formatPercent = (value: number | null, digits = 1): string =>
  value === null ? '-' : `${(value * 100).toFixed(digits)}%`;

const buildTestColumns = (
  t: TFunction,
): Array<{
  key: string;
  header: string;
  align?: 'left' | 'center' | 'right';
  render: (row: FactorResultRow) => React.ReactNode;
}> => [
  {
    key: 'factor',
    header: t('research.factorCard.columnFactor'),
    align: 'left',
    render: (r) => <span className={styles.factorName}>{r.factorName}</span>,
  },
  {
    key: 'period',
    header: t('research.factorCard.columnPeriod'),
    align: 'right',
    render: (r) => <span className={styles.numCell}>{String(r.period)}</span>,
  },
  {
    key: 'icMean',
    header: t('research.col.icMean'),
    align: 'right',
    render: (r) => (
      <span className={`${styles.numCell} ${styles.decision}`}>{formatNumber(r.icMean, 4)}</span>
    ),
  },
  {
    key: 'icStd',
    header: t('research.col.icStd'),
    align: 'right',
    render: (r) => <span className={styles.numCell}>{formatNumber(r.icStd, 4)}</span>,
  },
  {
    key: 'ir',
    header: t('research.col.ir'),
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
      <span className={`${styles.numCell} ${styles.decision}`}>{formatNumber(r.tStat, 3)}</span>
    ),
  },
  {
    key: 'pValue',
    header: t('metric.pValue'),
    align: 'right',
    render: (r) => (
      <span className={`${styles.numCell} ${styles.decision}`}>{formatNumber(r.pValue, 4)}</span>
    ),
  },
  {
    key: 'bhSignificant',
    header: t('metric.bhSignificant'),
    align: 'left',
    render: (r) => {
      if (r.bhSignificant === null) return <span className={styles.mutedCell}>—</span>;
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
];

export const ResearchPage = () => {
  const { t } = useTranslation();
  const TEST_COLUMNS = useMemo(() => buildTestColumns(t), [t]);

  /* ── 全局筛选状态 ── */
  const [variant, setVariant] = useState<string>('');
  const [testId, setTestId] = useState<string>('');
  const [sampleScope, setSampleScope] = useState<string>('');

  /* ── 因子区状态 ── */
  const [testsState, setTestsState] = useState<TestsState>(EMPTY_TESTS);
  const [selectedFactor, setSelectedFactor] = useState<FactorResultRow | null>(null);
  const [optionsState, setOptionsState] = useState<OptionsState>({ status: 'idle' });
  const [activeRunId, setActiveRunId] = useState<number | null>(null);
  const [filterOptionsState, setFilterOptionsState] = useState<OptionsState>({ status: 'idle' });

  /* ── 回测区状态 ── */
  const [btState, setBtState] = useState<BtState>(EMPTY_BT);
  const [expandedBacktest, setExpandedBacktest] = useState<BacktestSeriesQuery | null>(null);
  const [curveState, setCurveState] = useState<CurveState>({ status: 'idle' });

  const handleRowClick = (row: FactorResultRow): void => {
    setSelectedFactor(row);
  };

  const navigate = useNavigate();
  const handleRowDoubleClick = (row: FactorResultRow): void => {
    if (activeRunId === null) return;
    const search = new URLSearchParams({
      runId: String(activeRunId),
      variant: row.variantName,
      testId: row.testId,
      sampleScope: row.sampleScope,
      period: String(row.period),
    });
    navigate(`/research/factors/${encodeURIComponent(row.factorName)}?${search}`);
  };

  useEffect(() => {
    let cancelled = false;
    setOptionsState({ status: 'loading' });
    fetchResearchOptions()
      .then((data) => {
        if (cancelled) return;
        setOptionsState({ status: 'success', data });
        setFilterOptionsState({ status: 'success', data });
        setActiveRunId(data.defaultRunId);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
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
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (activeRunId === null) return;
    const controller = new AbortController();
    setVariant('');
    setTestId('');
    setSampleScope('');
    setFilterOptionsState({ status: 'loading' });
    fetchResearchOptions(activeRunId, controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return;
        setFilterOptionsState({ status: 'success', data });
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        if (error instanceof HttpError) {
          setFilterOptionsState({ status: 'error', error: error.apiError });
          return;
        }
        setFilterOptionsState({
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
  }, [activeRunId]);

  useEffect(() => {
    if (activeRunId === null) {
      setTestsState({ status: 'success', data: EMPTY_FACTOR_PAGE });
      return;
    }
    const controller = new AbortController();
    setTestsState({ status: 'loading' });
    setSelectedFactor(null);
    const validSampleScope =
      sampleScope === 'train' || sampleScope === 'test' ? sampleScope : undefined;
    fetchFactorResults(
      {
        runId: activeRunId,
        page: 1,
        pageSize: 25,
        ...(variant ? { variant } : {}),
        ...(testId ? { testId } : {}),
        ...(validSampleScope ? { sampleScope: validSampleScope } : {}),
      },
      controller.signal,
    )
      .then((data) => {
        setTestsState({ status: 'success', data });
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        if (error instanceof HttpError) {
          setTestsState({ status: 'error', error: error.apiError });
          return;
        }
        setTestsState({
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
  }, [activeRunId, variant, testId, sampleScope]);

  useEffect(() => {
    if (activeRunId === null) {
      setBtState({ status: 'success', data: { items: [], total: 0, page: 1, pageSize: 25 } });
      return;
    }
    const controller = new AbortController();
    setBtState({ status: 'loading' });
    fetchBacktestSummaries(
      {
        runId: activeRunId,
        page: 1,
        pageSize: 25,
        ...(variant ? { variant } : {}),
        ...(testId ? { testId } : {}),
      },
      controller.signal,
    )
      .then((data) => {
        if (!controller.signal.aborted) setBtState({ status: 'success', data });
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return;
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
  }, [activeRunId, variant, testId]);

  useEffect(() => {
    setExpandedBacktest(null);
  }, [activeRunId, variant, testId]);

  useEffect(() => {
    if (expandedBacktest === null) {
      setCurveState({ status: 'idle' });
      return;
    }
    const controller = new AbortController();
    setCurveState({ status: 'loading' });
    fetchBacktestSeries(expandedBacktest, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setCurveState({ status: 'success', data });
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return;
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
  }, [expandedBacktest]);

  const availableRuns = optionsState.status === 'success' ? optionsState.data.runs : [];
  const filterOptions = filterOptionsState.status === 'success' ? filterOptionsState.data : null;

  const selectedFactorBacktests =
    selectedFactor !== null && btState.status === 'success'
      ? btState.data.items.filter((item) => item.factorName === selectedFactor.factorName)
      : [];

  const factorTotal = testsState.status === 'success' ? testsState.data.total : null;
  const btTotal = btState.status === 'success' ? btState.data.total : null;

  return (
    <div className={styles.page}>
      <div className={styles.headerWrap}>
        <PageHeader title={t('research.title')} subtitle={t('research.subtitle')} />
      </div>

      {/* 全局筛选工具条 */}
      <div className={styles.toolbar} role="group" aria-label={t('research.filter.title')}>
        <div className={styles.filter}>
          <label className={styles.filterLabel} htmlFor="research-run">
            {t('research.filter.researchRun')}
          </label>
          <select
            id="research-run"
            className={styles.filterSelect}
            value={activeRunId ?? ''}
            disabled={optionsState.status === 'loading'}
            onChange={(e) => {
              const value = e.target.value;
              setActiveRunId(value === '' ? null : Number(value));
              setSelectedFactor(null);
            }}
          >
            <option value="">{t('research.filter.selectRun')}</option>
            {availableRuns.map((run) => (
              <option key={run.runId} value={run.runId}>
                {`Run ${run.runId} · ${run.createdAt}`}
              </option>
            ))}
          </select>
        </div>
        <div className={styles.filter}>
          <label className={styles.filterLabel} htmlFor="research-variant">
            {t('research.filter.variant')}
          </label>
          <select
            id="research-variant"
            className={styles.filterSelect}
            value={variant}
            disabled={filterOptionsState.status !== 'success'}
            onChange={(e) => setVariant(e.target.value)}
          >
            <option value="">{t('common.all')}</option>
            {filterOptions?.variants.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </div>
        <div className={styles.filter}>
          <label className={styles.filterLabel} htmlFor="research-test">
            {t('research.filter.testId')}
          </label>
          <select
            id="research-test"
            className={styles.filterSelect}
            value={testId}
            disabled={filterOptionsState.status !== 'success'}
            onChange={(e) => setTestId(e.target.value)}
          >
            <option value="">{t('common.all')}</option>
            {filterOptions?.testIds.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </div>
        <div className={styles.filter}>
          <label className={styles.filterLabel} htmlFor="research-scope">
            {t('research.filter.sampleScope')}
          </label>
          <select
            id="research-scope"
            className={styles.filterSelect}
            value={sampleScope}
            disabled={filterOptionsState.status !== 'success'}
            onChange={(e) => setSampleScope(e.target.value)}
          >
            <option value="">{t('common.all')}</option>
            {filterOptions?.sampleScopes.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </div>
        <div className={styles.runSummary}>
          <span className={styles.summaryDot} aria-hidden="true" />
          {activeRunId !== null
            ? t('research.summary', {
                runId: activeRunId,
                factors: factorTotal ?? '-',
                backtests: btTotal ?? '-',
              })
            : t('research.noRun')}
        </div>
      </div>

      {/* 主证据面板：因子 IC 与显著性 */}
      <section className={styles.panel} aria-label={t('research.factorCard.title')}>
        <div className={styles.panelHead}>
          <h2>{t('research.factorCard.title')}</h2>
          <span className={styles.panelMeta}>
            {activeRunId !== null
              ? t('research.factorMeta', { runId: activeRunId })
              : t('research.noRun')}
          </span>
        </div>

        <AsyncBoundary
          state={testsState}
          isEmpty={(data) => data.items.length === 0}
          emptyTitle={t('research.factorCard.emptyTitle')}
          emptyHint={t('research.emptyRunHint', { runId: activeRunId ?? '-' })}
        >
          {(data) => (
            <PaginatedTable
              columns={TEST_COLUMNS}
              page={data}
              rowKey={(row) => `${row.factorName}-${row.period}-${row.testId}`}
              onRowClick={handleRowClick}
              onRowDoubleClick={handleRowDoubleClick}
              selectedRowKey={
                selectedFactor
                  ? `${selectedFactor.factorName}-${selectedFactor.period}-${selectedFactor.testId}`
                  : undefined
              }
              onPageChange={(page) => {
                void page;
              }}
              emptyHint={t('research.factorCard.noMatch')}
            />
          )}
        </AsyncBoundary>

        {selectedFactor ? (
          <FactorLedger
            factor={selectedFactor}
            items={selectedFactorBacktests}
            onClose={() => setSelectedFactor(null)}
          />
        ) : null}
      </section>

      {/* 回测结果面板 */}
      <section className={styles.panel} aria-label={t('research.backtestCard.title')}>
        <div className={styles.panelHead}>
          <h2>{t('research.backtestCard.title')}</h2>
          <span className={styles.panelMeta}>{t('research.backtestCard.extra')}</span>
        </div>

        <AsyncBoundary
          state={btState}
          isEmpty={(d) => d.items.length === 0}
          emptyTitle={t('research.backtestCard.emptyTitle')}
          emptyHint={t('research.emptyRunHint', { runId: activeRunId ?? '-' })}
        >
          {(data) => (
            <BacktestSection
              items={data.items}
              expandedBacktest={expandedBacktest}
              curveState={curveState}
              onToggleCurve={(item) => {
                if (activeRunId === null) return;
                const next: BacktestSeriesQuery = {
                  runId: activeRunId,
                  variant: item.variantName,
                  backtestId: item.backtestId,
                  testId: item.testId,
                  factorName: item.factorName,
                  period: item.period,
                };
                setExpandedBacktest((current) =>
                  current?.backtestId === next.backtestId &&
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

/* ── 选中因子证据账本 ── */
const FactorLedger = ({
  factor,
  items,
  onClose,
}: {
  factor: FactorResultRow;
  items: BacktestSummaryCard[];
  onClose: () => void;
}) => {
  const { t } = useTranslation();
  return (
    <div className={styles.factorLedger}>
      <div className={styles.ledgerHead}>
        <div>
          <span className={styles.ledgerTitle}>
            {t('research.expand.selected')}
            <strong className={styles.ledgerFactor}>{factor.factorName}</strong>
          </span>
          <span className={styles.ledgerMeta}>
            {t('research.expand.meta', {
              period: factor.period,
              variant: factor.variantName,
              testId: factor.testId,
              sampleScope: factor.sampleScope,
            })}
          </span>
        </div>
        <button type="button" className={styles.closeBtn} onClick={onClose}>
          {t('research.expand.close')}
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none" aria-hidden="true">
            <path d="M2 2l6 6M8 2l-6 6" stroke="currentColor" strokeWidth={1.2} />
          </svg>
        </button>
      </div>

      <div className={styles.kpiRow}>
        <ExpandKpi label={t('research.col.icMean')} value={formatNumber(factor.icMean, 4)} />
        <ExpandKpi label={t('research.col.icStd')} value={formatNumber(factor.icStd, 4)} />
        <ExpandKpi label={t('research.col.ir')} value={formatNumber(factor.ir, 4)} />
        <ExpandKpi label={t('metric.tStat')} value={formatNumber(factor.tStat, 3)} />
        <ExpandKpi label={t('metric.pValue')} value={formatNumber(factor.pValue, 4)} />
        <ExpandKpi
          label={t('metric.bhSignificant')}
          value={
            factor.bhSignificant === null
              ? '—'
              : factor.bhSignificant
                ? t('research.significant')
                : t('research.notSignificant')
          }
          significance={factor.bhSignificant === true}
        />
      </div>

      <div className={styles.relatedHead}>
        {t('research.expand.backtestCount', { count: items.length })}
      </div>
      {items.length === 0 ? (
        <div className={styles.relatedEmpty}>
          {t('research.expand.noBacktest', { factor: factor.factorName })}
        </div>
      ) : (
        <div className={styles.btMiniRow}>
          {items.map((item) => (
            <BtMiniCard key={`${item.backtestId}-${item.factorName}-${item.period}`} item={item} />
          ))}
        </div>
      )}
    </div>
  );
};

const ExpandKpi = ({
  label,
  value,
  significance,
}: {
  label: string;
  value: string;
  significance?: boolean;
}) => (
  <div className={styles.kpi}>
    <span className={styles.kpiLabel}>{label}</span>
    <span className={significance ? `${styles.kpiValue} ${styles.kpiSigOn}` : styles.kpiValue}>
      {significance ? <span className={styles.sigDot} aria-hidden="true" /> : null}
      {value}
    </span>
  </div>
);

const BtMiniCard = ({ item }: { item: BacktestSummaryCard }) => {
  const { t } = useTranslation();
  const quantiles = Object.entries(item.quantileYearlyReturns).filter(
    ([key]) => /^Q[15]$/.test(key) || key === 'longShort',
  );
  const entries = quantiles.length > 0 ? quantiles : Object.entries(item.quantileYearlyReturns);
  return (
    <div className={styles.btMini}>
      <div className={styles.btMiniHead}>
        <span className={styles.btMiniFactor}>{item.factorName}</span>
        <span className={styles.btMiniJob}>{item.backtestId}</span>
      </div>
      <div className={styles.btMiniQuantiles}>
        {entries.map(([key, value]) => (
          <div key={key} className={styles.btMiniQ}>
            <span className={styles.btMiniQl}>
              {key === 'longShort' ? t('research.col.longShort') : key}
            </span>
            <span className={styles.btMiniQv}>{formatPercent(value, 2)}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

/* ── 回测结果区 ── */
const BacktestSection = ({
  items,
  expandedBacktest,
  curveState,
  onToggleCurve,
}: {
  items: BacktestSummaryCard[];
  expandedBacktest: BacktestSeriesQuery | null;
  curveState: CurveState;
  onToggleCurve: (item: BacktestSummaryCard) => void;
}) => {
  const { t } = useTranslation();
  if (items.length === 0) {
    return <div className={styles.btEmpty}>{t('research.backtestCard.empty')}</div>;
  }
  return (
    <div className={styles.btGrid}>
      {items.map((item) => {
        const isExpanded =
          expandedBacktest?.backtestId === item.backtestId &&
          expandedBacktest.factorName === item.factorName &&
          expandedBacktest.period === item.period;
        return (
          <Fragment key={`${item.backtestId}-${item.factorName}-${item.period}`}>
            <BtMetricCard
              item={item}
              isExpanded={isExpanded}
              onToggleCurve={() => onToggleCurve(item)}
            />
            {isExpanded && expandedBacktest ? (
              <BacktestCurvePanel query={expandedBacktest} state={curveState} />
            ) : null}
          </Fragment>
        );
      })}
    </div>
  );
};

const BacktestCurvePanel = ({
  query,
  state,
}: {
  query: BacktestSeriesQuery;
  state: CurveState;
}) => {
  const { t } = useTranslation();
  return (
    <div className={styles.curvePanel}>
      <div className={styles.curveTitle}>
        {t('research.curve.title', { factor: query.factorName, period: query.period })}
      </div>
      <AsyncBoundary
        state={state}
        isEmpty={(data) => data.series.length === 0}
        emptyTitle={t('research.curve.emptyTitle')}
        emptyHint={t('research.curve.emptyHint')}
      >
        {(data) => (
          <SeriesChart
            series={data.series}
            baseDate={data.baseDate ?? undefined}
            height={260}
            drawEffect
          />
        )}
      </AsyncBoundary>
    </div>
  );
};

const BtMetricCard = ({
  item,
  isExpanded,
  onToggleCurve,
}: {
  item: BacktestSummaryCard;
  isExpanded?: boolean;
  onToggleCurve?: () => void;
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
            <span className={styles.btQv}>{formatPercent(value, 2)}</span>
          </div>
        ))}
      </div>

      <div className={styles.btStats}>
        <BtStat label={t('metric.sharpe')} value={formatNumber(item.sharpe, 2)} />
        <BtStat label={t('metric.maxDrawdown')} value={formatPercent(item.maxDrawdown)} />
        <BtStat label={t('metric.winRate')} value={formatPercent(item.winRate)} />
        <BtStat
          label={t('metric.holdingPeriod')}
          value={t('metric.days', { count: item.period })}
        />
      </div>

      {onToggleCurve ? (
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
      ) : null}
    </div>
  );
};

const BtStat = ({ label, value }: { label: string; value: string }) => (
  <div className={styles.btStat}>
    <span className={styles.btSl}>{label}</span>
    <span className={styles.btSv}>{value}</span>
  </div>
);

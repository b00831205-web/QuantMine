/**
 * 调仓收益页 · Evidence Ledger（证据账本）
 *
 * 方向契约：
 * THESIS：所选调仓的收益曲线是页面唯一的主证据区，筛选与记录浏览退居第二块账本面板。
 * OWN-WORLD：沿用 DESIGN.md 的哑光深色研究终端语言——平层色阶、1px 细线、
 *         钴蓝只用于选中与交互，收益数字保持中性 ± 而不做红绿 P&L 配色。
 * STORY：研究员从记录账本里选中一期调仓，曲线与贡献栏随即更新为该期证据。
 * FIRST VIEWPORT：紧凑页头 + 曲线主面板（面板头 → 走势图 → 指标账本），
 *         记录面板（筛选工具条 + 列表/贡献栏）在首屏之下。
 * FORM：Evidence Ledger，与已认可的市场总览 template 同构。
 * FINISH：unreviewed and undocumented is unfinished；本次以类型/测试/构建与人工视觉复核收口。
 */

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { PageHeader } from '@/components/common/PageHeader';
import { AsyncBoundary } from '@/components/common/AsyncBoundary';
import { HttpError } from '@/api/http';
import {
  fetchRebalances,
  fetchRebalanceDetail,
  fetchRebalanceReturns,
  fetchSeries,
} from '@/api/client';
import type { AsyncState, Unit } from '@/types/api';
import type {
  RebalancePage as RebalancePageData,
  RebalanceDetail,
  RebalanceSummary,
} from '@/types/rebalance';
import type { SeriesPoint, SeriesResponse } from '@/types/market';
import { SeriesChart } from '@/components/chart/SeriesChart';
import { PaginatedTable } from '@/components/common/PaginatedTable';
import type { Column } from '@/components/common/PaginatedTable';
import i18n from '@/i18n';
import styles from './RebalancePage.module.css';

/** 收益数字统一带正负号，中性文本色 */
const formatReturn = (value: number, unit: Unit): string => {
  const pct = unit === 'percent' ? value : value * 100;
  return `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`;
};

const REBALANCE_COLUMNS: Column<RebalanceSummary>[] = [
  {
    key: 'rebalanceDate',
    header: i18n.t('rebalance.col.date'),
    align: 'left',
    render: (r) => <span className={styles.dateCell}>{r.rebalanceDate}</span>,
  },
  {
    key: 'variant',
    header: i18n.t('rebalance.col.variant'),
    align: 'left',
    render: (r) => <span className={styles.textCell}>{r.variant}</span>,
  },
  {
    // Sits next to Variant because that is where the ambiguity is: two backtest
    // jobs can share a variant, and then only the weighting scheme tells the
    // rows apart -- while it is the thing that decides every position size.
    key: 'weighting',
    header: i18n.t('rebalance.col.weighting'),
    align: 'left',
    render: (r) => (
      <span className={styles.textCell}>
        {r.weighting
          ? i18n.t(`rebalance.weighting.${r.weighting}`, { defaultValue: r.weighting })
          : '—'}
      </span>
    ),
  },
  {
    key: 'holdingPeriod',
    header: i18n.t('rebalance.col.holdingPeriod'),
    align: 'right',
    render: (r) => <span className={styles.numCell}>{r.holdingPeriod}d</span>,
  },
  {
    key: 'quantile',
    header: i18n.t('rebalance.col.quantile'),
    align: 'center',
    render: (r) => <span className={styles.qBadge}>{r.quantile}</span>,
  },
  {
    key: 'netReturn',
    header: i18n.t('rebalance.col.netReturn'),
    align: 'right',
    render: (r) => (
      <span className={`${styles.numCell} ${styles.decision}`}>
        {formatReturn(r.netReturn, r.unit)}
      </span>
    ),
  },
  {
    key: 'spyReturn',
    header: 'SPY',
    align: 'right',
    render: (r) => <span className={styles.numCell}>{formatReturn(r.spyReturn, r.unit)}</span>,
  },
  {
    key: 'excessReturn',
    header: i18n.t('rebalance.col.excess'),
    align: 'right',
    render: (r) => (
      <span className={`${styles.numCell} ${styles.decision}`}>
        {formatReturn(r.excessReturn, r.unit)}
      </span>
    ),
  },
  {
    key: 'turnover',
    header: i18n.t('rebalance.col.turnover'),
    align: 'right',
    render: (r) => <span className={styles.numCell}>{(r.turnover * 100).toFixed(1)}%</span>,
  },
  {
    key: 'holdingsCount',
    header: i18n.t('rebalance.col.holdings'),
    align: 'right',
    render: (r) => (
      <span className={styles.numCell}>{r.quantile === 'LS' ? '—' : String(r.holdingsCount)}</span>
    ),
  },
  {
    key: 'tradingDaysToNext',
    header: i18n.t('rebalance.col.daysToNext'),
    align: 'right',
    render: (r) => <span className={styles.numCell}>{String(r.tradingDaysToNext)}</span>,
  },
];

export const RebalancePage = () => {
  const { t } = useTranslation();
  const [listState, setListState] = useState<AsyncState<RebalancePageData>>({ status: 'idle' });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [returnState, setReturnState] = useState<AsyncState<{ series: SeriesPoint[] }>>({
    status: 'idle',
  });
  const [spyState, setSpyState] = useState<AsyncState<SeriesResponse>>({ status: 'idle' });
  const [detailState, setDetailState] = useState<AsyncState<RebalanceDetail>>({ status: 'idle' });
  const [backtestJob, setBacktestJob] = useState('');
  const [variant, setVariant] = useState('');
  const [factor, setFactor] = useState('');
  const [searchDate, setSearchDate] = useState('');
  const [page, setPage] = useState(1);

  const filterOptions =
    listState.status === 'success'
      ? {
          backtestJob: Array.from(new Set(listState.data.items.map((r) => r.backtestJob))),
          variants: Array.from(new Set(listState.data.items.map((r) => r.variant))),
          factors: Array.from(new Set(listState.data.items.map((r) => r.factor))),
        }
      : { backtestJob: [], variants: [], factors: [] };

  const navigate = useNavigate();

  useEffect(() => {
    if (selectedId === null) {
      setDetailState({ status: 'idle' });
      return;
    }
    const controller = new AbortController();
    setDetailState({ status: 'loading' });
    fetchRebalanceDetail(selectedId, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setDetailState({ status: 'success', data });
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        if (error instanceof HttpError) {
          setDetailState({ status: 'error', error: error.apiError });
          return;
        }
        setDetailState({
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
  }, [selectedId]);

  useEffect(() => {
    const controller = new AbortController();
    setListState({ status: 'loading' });
    fetchRebalances(
      {
        page,
        pageSize: 20,
        ...(backtestJob ? { backtestJob } : {}),
        ...(variant ? { variant } : {}),
        ...(factor ? { factor } : {}),
        ...(searchDate ? { tradeDate: searchDate } : {}),
      },
      controller.signal,
    )
      .then((data) => {
        if (!controller.signal.aborted) {
          setListState({ status: 'success', data });
          setSelectedId((prev) => prev ?? data.items[0]?.rebalanceId ?? null);
        }
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        if (error instanceof HttpError) {
          setListState({ status: 'error', error: error.apiError });
          return;
        }
        setListState({
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
  }, [backtestJob, variant, factor, searchDate, page]);

  // 筛选/搜索变化时，回到第一页并清空选中
  useEffect(() => {
    setSelectedId(null);
    setPage(1);
  }, [backtestJob, variant, factor, searchDate]);

  useEffect(() => {
    if (selectedId === null) {
      setReturnState({ status: 'idle' });
      return;
    }
    const controller = new AbortController();
    setReturnState({ status: 'loading' });
    fetchRebalanceReturns(selectedId, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setReturnState({ status: 'success', data });
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        if (error instanceof HttpError) {
          setReturnState({ status: 'error', error: error.apiError });
          return;
        }
        setReturnState({
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
  }, [selectedId]);

  useEffect(() => {
    if (returnState.status !== 'success' || returnState.data.series.length === 0) {
      setSpyState({ status: 'idle' });
      return;
    }
    const controller = new AbortController();
    setSpyState({ status: 'loading' });

    const series = returnState.data.series;
    const firstPoint = series[0];
    const lastPoint = series[series.length - 1];
    if (firstPoint === undefined || lastPoint === undefined) {
      setSpyState({ status: 'idle' });
      return;
    }
    const startDate = firstPoint.date;
    const endDate = lastPoint.date;

    fetchSeries({ symbols: ['SPY'], startDate, endDate }, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setSpyState({ status: 'success', data });
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        if (error instanceof HttpError) {
          setSpyState({ status: 'error', error: error.apiError });
          return;
        }
        setSpyState({
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
  }, [returnState]);

  const selectedSummary =
    (listState.status === 'success'
      ? listState.data.items.find((r) => r.rebalanceId === selectedId)
      : undefined) ??
    (detailState.status === 'success' ? detailState.data : undefined) ??
    null;

  const panelMeta = selectedSummary
    ? t('rebalance.meta', {
        date: selectedSummary.rebalanceDate,
        variant: selectedSummary.variant,
        quantile: selectedSummary.quantile,
        holdingPeriod: selectedSummary.holdingPeriod,
      })
    : t('rebalance.noSelection');

  const countText =
    listState.status === 'success'
      ? t('rebalance.count', {
          total: listState.data.total,
          date: listState.data.items[0]?.rebalanceDate ?? '-',
        })
      : t('rebalance.countPlaceholder');

  return (
    <div className={styles.page}>
      <div className={styles.headerWrap}>
        <PageHeader title={t('nav.rebalance')} subtitle={t('rebalance.subtitle')} />
      </div>

      <section className={styles.panel} aria-label={t('rebalance.curveTitle')}>
        <div className={styles.panelHead}>
          <h2>{t('rebalance.curveTitle')}</h2>
          <span className={styles.panelMeta}>{panelMeta}</span>
        </div>

        <div className={styles.chartWrap}>
          <AsyncBoundary
            state={returnState}
            isEmpty={(d) => d.series.length === 0}
            emptyTitle={t('rebalance.noCurve')}
            emptyHint={t('rebalance.curveHint')}
          >
            {(data) => {
              const spySeries = spyState.status === 'success' ? spyState.data.series : [];
              return (
                <SeriesChart
                  series={[{ symbol: t('rebalance.portfolio'), points: data.series }, ...spySeries]}
                  height={300}
                  drawEffect
                />
              );
            }}
          </AsyncBoundary>
        </div>

        <div className={styles.ledger}>
          <LedgerCell
            primary
            label={t('rebalance.ledger.net')}
            value={
              selectedSummary ? formatReturn(selectedSummary.netReturn, selectedSummary.unit) : '-'
            }
            note={
              selectedSummary
                ? t('rebalance.ledger.netNote', {
                    holdingPeriod: selectedSummary.holdingPeriod,
                  })
                : t('rebalance.ledger.baseNote')
            }
          />
          <LedgerCell
            label={t('rebalance.ledger.spy')}
            value={
              selectedSummary ? formatReturn(selectedSummary.spyReturn, selectedSummary.unit) : '-'
            }
            note={t('rebalance.ledger.spyNote')}
          />
          <LedgerCell
            label={t('rebalance.ledger.excess')}
            value={
              selectedSummary
                ? formatReturn(selectedSummary.excessReturn, selectedSummary.unit)
                : '-'
            }
            note={t('rebalance.ledger.excessNote')}
          />
          <LedgerCell
            label={t('rebalance.ledger.turnover')}
            value={selectedSummary ? `${(selectedSummary.turnover * 100).toFixed(1)}%` : '-'}
            note={t('rebalance.ledger.turnoverNote')}
          />
          <LedgerCell
            label={t('rebalance.ledger.holdings')}
            value={
              selectedSummary
                ? selectedSummary.quantile === 'LS'
                  ? '—'
                  : String(selectedSummary.holdingsCount)
                : '-'
            }
            note={
              selectedSummary
                ? selectedSummary.quantile === 'LS'
                  ? t('rebalance.ledger.lsNote')
                  : t('rebalance.ledger.nextNote', {
                      days: selectedSummary.tradingDaysToNext,
                    })
                : undefined
            }
          />
        </div>
      </section>

      <section className={styles.records} aria-label={t('rebalance.recordsTitle')}>
        <div className={styles.recordsHead}>
          <h2>{t('rebalance.recordsTitle')}</h2>
          <span className={styles.count}>{countText}</span>
        </div>

        <div className={styles.filterBar}>
          <div className={styles.filter}>
            <label className={styles.filterLabel} htmlFor="rebalance-date">
              {t('rebalance.filter.date')}
            </label>
            <div className={styles.dateWithClear}>
              <input
                id="rebalance-date"
                type="date"
                value={searchDate}
                onChange={(e) => setSearchDate(e.target.value)}
                aria-label={t('rebalance.filter.dateSearch')}
              />
              {searchDate ? (
                <button
                  type="button"
                  className={styles.clearBtn}
                  onClick={() => setSearchDate('')}
                  title={t('rebalance.clear')}
                  aria-label={t('rebalance.clear')}
                >
                  ×
                </button>
              ) : null}
            </div>
          </div>
          <div className={styles.filter}>
            <label className={styles.filterLabel} htmlFor="rebalance-job">
              {t('rebalance.filter.job')}
            </label>
            <select
              id="rebalance-job"
              value={backtestJob}
              onChange={(e) => setBacktestJob(e.target.value)}
            >
              <option value="">{t('common.all')}</option>
              {filterOptions.backtestJob.map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </select>
          </div>
          <div className={styles.filter}>
            <label className={styles.filterLabel} htmlFor="rebalance-variant">
              {t('rebalance.filter.variant')}
            </label>
            <select
              id="rebalance-variant"
              value={variant}
              onChange={(e) => setVariant(e.target.value)}
            >
              <option value="">{t('common.all')}</option>
              {filterOptions.variants.map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </select>
          </div>
          <div className={styles.filter}>
            <label className={styles.filterLabel} htmlFor="rebalance-factor">
              {t('rebalance.filter.factor')}
            </label>
            <select
              id="rebalance-factor"
              value={factor}
              onChange={(e) => setFactor(e.target.value)}
            >
              <option value="">{t('common.all')}</option>
              {filterOptions.factors.map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className={styles.split}>
          <div className={styles.listCol}>
            <AsyncBoundary
              state={listState}
              isEmpty={(data) => data.items.length === 0}
              emptyTitle={t('rebalance.noRecords')}
              emptyHint={t('rebalance.recordsHint')}
            >
              {(data) => (
                <PaginatedTable
                  columns={REBALANCE_COLUMNS}
                  page={data}
                  onPageChange={(p) => setPage(p)}
                  rowKey={(row) => row.rebalanceId}
                  onRowClick={(row) => setSelectedId(row.rebalanceId)}
                  onRowDoubleClick={(row) => {
                    // LS（多空组合）没有单独持仓，详情页无内容可看，不跳转
                    if (row.quantile === 'LS') return;
                    navigate(`/rebalance/${row.rebalanceId}`);
                  }}
                  selectedRowKey={selectedId ?? undefined}
                  emptyHint={t('rebalance.noRecords')}
                />
              )}
            </AsyncBoundary>
          </div>

          <aside className={styles.rail}>
            <div className={styles.railHead}>
              <h3 className={styles.railTitle}>{t('rebalance.topTitle')}</h3>
              <span className={styles.railHint}>{t('rebalance.topHint')}</span>
            </div>
            <AsyncBoundary state={detailState}>
              {(detail) => {
                // 以持仓为主，关联前向收益（contributions）。最新一期没有下一期价格 →
                // 无 contributions，此时仍展示持仓、收益列显示「—」。
                const contribBySymbol = new Map(
                  detail.contributions.map((c) => [c.symbol, c.contribution]),
                );
                const hasContrib = detail.contributions.length > 0;
                const rows = detail.holdings.map((h) => ({
                  symbol: h.symbol,
                  quantile: h.quantile ?? '-',
                  contribution: contribBySymbol.get(h.symbol) ?? null,
                }));
                const top = (
                  hasContrib
                    ? rows.sort(
                        (a, b) => (b.contribution ?? -Infinity) - (a.contribution ?? -Infinity),
                      )
                    : rows
                ).slice(0, 20);

                if (top.length === 0) {
                  // 别把"产物找不到"说成"本期没有独立持仓"——那是把故障伪装成正常，
                  // 排查的人会去翻回测逻辑，而真正的原因往往只是 data 目录没挂载。
                  const emptyKey =
                    detail.holdingsStatus === 'artifact_missing'
                      ? 'rebalance.railMissingArtifact'
                      : 'rebalance.railEmpty';
                  return <div className={styles.railEmpty}>{t(emptyKey)}</div>;
                }

                return (
                  <>
                    <div className={styles.railTableWrap}>
                      <table className={styles.railTable}>
                        <thead>
                          <tr>
                            <th>#</th>
                            <th>Ticker</th>
                            <th>{t('rebalance.col.quantile')}</th>
                            <th className={styles.contribHead}>{t('rebalance.col.return')}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {top.map((r, index) => (
                            <tr key={r.symbol}>
                              <td className={styles.rank}>{index + 1}</td>
                              <td className={styles.tickerCell}>{r.symbol}</td>
                              <td>
                                <span className={styles.qBadge}>{r.quantile}</span>
                              </td>
                              <td
                                className={styles.contrib}
                                style={
                                  !hasContrib || r.contribution === null
                                    ? { color: 'var(--text-muted)' }
                                    : undefined
                                }
                              >
                                {!hasContrib
                                  ? t('rebalance.notApplicable')
                                  : r.contribution === null
                                    ? '—'
                                    : formatReturn(r.contribution, detail.unit)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <div className={styles.railNote}>
                      {t('rebalance.railNote', {
                        shown: top.length,
                        total: detail.holdings.length,
                      })}
                      {detail.quantile !== 'LS' && selectedId !== null ? (
                        <>
                          {' · '}
                          <button
                            type="button"
                            className={styles.linkBtn}
                            onClick={() => navigate(`/rebalance/${selectedId}`)}
                          >
                            {t('rebalance.viewHoldings')}
                          </button>
                        </>
                      ) : null}
                    </div>
                  </>
                );
              }}
            </AsyncBoundary>
          </aside>
        </div>
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
  note,
  primary = false,
}: {
  label: string;
  value: string;
  note?: string | undefined;
  primary?: boolean;
}) => {
  const cellClass = primary
    ? `${styles.ledgerCell} ${styles.ledgerCellPrimary}`
    : styles.ledgerCell;
  return (
    <div className={cellClass}>
      <div className={styles.ledgerLabel}>{label}</div>
      <div className={styles.ledgerValue}>{value}</div>
      {note ? <div className={styles.ledgerNote}>{note}</div> : null}
    </div>
  );
};

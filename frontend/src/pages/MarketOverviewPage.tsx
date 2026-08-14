/**
 * 市场总览页 · Evidence Ledger（证据账本）
 *
 * 方向契约：
 * THESIS：市场比较图是页面唯一的主证据区，筛选工具与辅助指标退居账本行，
 *         拒绝五张等重 KPI 卡片。
 * OWN-WORLD：沿用 DESIGN.md 的哑光深色研究终端语言——平层色阶、1px 细线、
 *         钴蓝只用于交互与焦点，所有机器值使用等宽数字。
 * STORY：研究员一眼看到图表结论，工具条在同一面板内完成组合筛选，
 *         指标账本紧贴图表给出证据上下文。
 * FIRST VIEWPORT：紧凑页头 + 单块带边框主面板（面板头 → 工具条 → 图表 → 底部账本）。
 * FORM：Evidence Ledger，DESIGN.md 默认工作台方向。
 * FINISH：unreviewed and undocumented is unfinished；本次以类型/测试/构建与人工视觉复核收口。
 */

import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import i18n from '@/i18n';
import { PageHeader } from '@/components/common/PageHeader';
import { AsyncBoundary } from '@/components/common/AsyncBoundary';
import { SeriesChart } from '@/components/chart/SeriesChart';
import { fetchSeries, fetchLatestMarketDate, fetchMarketOverview } from '@/api/client/market';
import { fetchWorkflows } from '@/api/client';
import { runAwarePollMs, usePolledAsync } from '@/hooks/usePolledAsync';
import type { AsyncState } from '@/types/api';
import type { MarketOverview, SeriesQuery, SeriesResponse } from '@/types/market';
import { isActiveState, stateColor, stateLabel } from '@/utils/workflowStatus';
import { HttpError } from '@/api/http';
import { Plus, X } from 'lucide-react';
import styles from './MarketOverviewPage.module.css';

type RangeKey = '1M' | '1Y' | '5Y' | 'ALL';

const INITIAL_SYMBOLS = ['SPY', 'AAPL', 'MSFT'];

const RANGE_KEYS: RangeKey[] = ['1M', '1Y', '5Y', 'ALL'];

const RANGE_DAYS: Record<RangeKey, number | 'ALL'> = {
  '1M': 30,
  '1Y': 365,
  '5Y': 365 * 5,
  ALL: 'ALL',
};

/**
 * 市场总览页：一个主证据面板承载对比图表，筛选工具与指标账本都在面板内。
 */
export const MarketOverviewPage = () => {
  const { t } = useTranslation();

  // —— 视图状态 ——
  const [symbols, setSymbols] = useState<string[]>(INITIAL_SYMBOLS);
  const [range, setRange] = useState<RangeKey>('1Y');
  const [tickerDraft, setTickerDraft] = useState('');
  // 错误重试时强制重新拉取序列数据
  const [reloadKey, setReloadKey] = useState(0);

  // —— 数据状态 ——
  const [seriesState, setSeriesState] = useState<AsyncState<SeriesResponse>>({ status: 'idle' });

  // 这三项以前都只在挂载时取一次，合起来的后果不是"少刷新一次"，而是页面永久空白：
  // 库还空着时 /market/latest-date 返回 **404**（不是 null），取数直接 reject 且原来
  // 没有 catch，latestTradeDate 停在 null → query 为 null → 序列请求根本不发 →
  // 图表停在 idle。而"先起服务、再跑 DAG"正是新用户的必经路径，于是跑完了页面依旧
  // 空白，且连一次失败的网络请求都看不到，看起来像产品坏了。
  //
  // 只轮询这三个便宜的接口；序列（单次约 36KB）不轮询——它的 query 由 latestTradeDate
  // 推导，日期一变就会自动重取，没必要额外定时打它。
  const [hasActiveRun, setHasActiveRun] = useState(false);
  const pollMs = runAwarePollMs(hasActiveRun);

  const workflowsPoll = usePolledAsync((s) => fetchWorkflows(s), [], { pollMs });
  const latestDatePoll = usePolledAsync((s) => fetchLatestMarketDate(s), [], { pollMs });
  const overviewPoll = usePolledAsync((s) => fetchMarketOverview(s), [], { pollMs });

  const latestTradeDate =
    latestDatePoll.state.status === 'success' ? latestDatePoll.state.data.latestTradeDate : null;
  const overview: MarketOverview | null =
    overviewPoll.state.status === 'success' ? overviewPoll.state.data : null;

  const latestRun = useMemo(() => {
    if (workflowsPoll.state.status !== 'success') return null;
    const runs = workflowsPoll.state.data
      .flatMap((dag) => dag.recentRuns ?? [])
      .filter((run) => run.startDate !== null)
      .sort((a, b) => (b.startDate! > a.startDate! ? 1 : -1));
    return runs[0] ?? null;
  }, [workflowsPoll.state]);

  useEffect(() => {
    setHasActiveRun(isActiveState(latestRun?.state));
  }, [latestRun]);

  const taskStatus = latestRun
    ? { label: stateLabel(latestRun.state), color: stateColor(latestRun.state) }
    : null;

  const query = useMemo<SeriesQuery | null>(() => {
    if (latestTradeDate === null) return null;
    const endDate = latestTradeDate;
    const end = new Date(`${latestTradeDate}T00:00:00Z`);
    const days = RANGE_DAYS[range];
    if (days === 'ALL') {
      return { symbols, startDate: '2015-01-01', endDate, normalize: true };
    }
    const start = new Date(end.getTime() - days * 86400_000).toISOString().slice(0, 10);
    return { symbols, startDate: start, endDate, normalize: true };
  }, [latestTradeDate, symbols, range]);

  useEffect(() => {
    if (query === null) return;

    const controller = new AbortController();
    setSeriesState({ status: 'loading' });

    fetchSeries(query, controller.signal)
      .then((data) => {
        setSeriesState({ status: 'success', data });
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return;

        if (error instanceof HttpError) {
          setSeriesState({ status: 'error', error: error.apiError });
          return;
        }

        setSeriesState({
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
  }, [latestTradeDate, symbols, range, query, reloadKey]);

  const handleAddTicker = (): void => {
    const ticker = tickerDraft.trim().toUpperCase();
    if (!ticker || symbols.includes(ticker)) return;
    setSymbols([...symbols, ticker]);
    setTickerDraft('');
  };

  const handleRemoveTicker = (symbol: string): void => {
    setSymbols(symbols.filter((s) => s !== symbol));
  };

  const spyDailyReturn = (() => {
    if (seriesState.status !== 'success') return null;
    const spySeries = seriesState.data.series.find((s) => s.symbol === 'SPY');
    const latestPoint = spySeries?.points.at(-1);
    const previousPoint = spySeries?.points.at(-2);
    if (latestPoint === undefined || previousPoint === undefined || previousPoint.value === 0) {
      return null;
    }
    return (latestPoint.value / previousPoint.value - 1) * 100;
  })();

  const spyDailyReturnLabel =
    spyDailyReturn === null
      ? '-'
      : `${spyDailyReturn >= 0 ? '+' : ''}${spyDailyReturn.toFixed(2)}%`;

  return (
    <div className={styles.page}>
      <div className={styles.headerWrap}>
        <PageHeader title={t('market.title')} subtitle={t('market.subtitle')} />
      </div>

      <section className={styles.panel} aria-label={t('market.compareCard')}>
        <div className={styles.panelHead}>
          <h2>{t('market.compareCard')}</h2>
          <span className={styles.panelDate}>
            <span className={styles.panelDateLabel}>{t('market.kpi.latestDate')}</span>
            <span className={styles.panelDateValue}>{latestTradeDate ?? '-'}</span>
          </span>
        </div>

        <div className={styles.toolbar}>
          <div className={styles.tickerGroup}>
            {symbols.map((symbol) => (
              <span key={symbol} className={styles.chip}>
                {symbol}
                <button
                  type="button"
                  className={styles.chipX}
                  onClick={() => handleRemoveTicker(symbol)}
                  aria-label={t('market.removeTicker', { symbol })}
                >
                  <X size={10} strokeWidth={1.75} aria-hidden="true" />
                </button>
              </span>
            ))}
            <div className={styles.addTicker}>
              <input
                type="text"
                placeholder={t('market.addTickerPlaceholder')}
                value={tickerDraft}
                onChange={(e) => setTickerDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleAddTicker();
                }}
              />
              <button type="button" onClick={handleAddTicker}>
                <Plus size={12} strokeWidth={1.75} aria-hidden="true" />
                {t('market.add')}
              </button>
            </div>
          </div>

          <div className={styles.rangeGroup} role="group" aria-label={t('market.timeRange')}>
            {RANGE_KEYS.map((r) => (
              <button
                key={r}
                type="button"
                className={range === r ? styles.rangeActive : styles.rangeBtn}
                aria-pressed={range === r}
                onClick={() => setRange(r)}
              >
                {r}
              </button>
            ))}
          </div>
        </div>

        <div className={styles.chartWrap}>
          <AsyncBoundary
            state={seriesState}
            isEmpty={(d) => d.series.length === 0}
            onRetry={() => setReloadKey((k) => k + 1)}
            emptyTitle={t('market.emptyTitle')}
            emptyHint={t('market.rangeHint', {
              start: query?.startDate ?? '-',
              end: query?.endDate ?? '-',
            })}
          >
            {(data) => (
              <SeriesChart
                series={data.series}
                height={360}
                drawEffect
                onReset={() => {
                  setSymbols(INITIAL_SYMBOLS);
                  setRange('1Y');
                }}
              />
            )}
          </AsyncBoundary>
        </div>

        <div className={styles.ledger}>
          <LedgerCell
            primary
            label={t('market.kpi.latestDate')}
            value={latestTradeDate ?? '-'}
            note={overview ? t('market.kpi.constituents', { total: overview.total }) : undefined}
          />
          <LedgerCell
            label={t('market.kpi.dailyReturn')}
            value={spyDailyReturnLabel}
            note={t('market.kpi.normalizeBase')}
          />
          <LedgerCell
            label={t('market.kpi.advancers')}
            value={overview ? `${overview.advancers} / ${overview.total}` : '-'}
            note={overview ? t('market.kpi.decliners', { count: overview.decliners }) : undefined}
          />
          <LedgerCell
            label={t('market.kpi.breadth')}
            value={overview ? `${(overview.breadth * 100).toFixed(1)}%` : '-'}
            note={t('market.kpi.breadthNote')}
          />
          <LedgerCell
            label={t('market.kpi.taskStatus')}
            value={taskStatus ? taskStatus.label : t('market.kpi.notRun')}
            valueColor={taskStatus?.color}
            taskState={taskStatus !== null}
          />
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
  valueColor,
  taskState = false,
}: {
  label: string;
  value: string;
  note?: string | undefined;
  primary?: boolean;
  valueColor?: string | undefined;
  taskState?: boolean;
}) => {
  const cellClass = primary
    ? `${styles.ledgerCell} ${styles.ledgerCellPrimary}`
    : styles.ledgerCell;
  return (
    <div className={cellClass}>
      <div className={styles.ledgerLabel}>{label}</div>
      <div className={styles.ledgerValue} style={valueColor ? { color: valueColor } : undefined}>
        {taskState ? (
          <span
            className={styles.taskDot}
            style={valueColor ? { background: valueColor } : undefined}
            aria-hidden="true"
          />
        ) : null}
        {value}
      </div>
      {note ? <div className={styles.ledgerNote}>{note}</div> : null}
    </div>
  );
};

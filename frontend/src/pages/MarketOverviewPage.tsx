import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import i18n from '@/i18n';
import { PageHeader } from '@/components/common/PageHeader';
import { Card } from '@/components/common/Card';
import { AsyncBoundary } from '@/components/common/AsyncBoundary';
import { SeriesChart } from '@/components/chart/SeriesChart';
import { fetchSeries, fetchLatestMarketDate, fetchMarketOverview } from '@/api/client/market';
import { fetchWorkflows } from '@/api/client';
import type { AsyncState, ApiError } from '@/types/api';
import type { SeriesQuery, SeriesResponse, MarketOverview } from '@/types/market';
import { stateLabel, stateColor } from '@/utils/workflowStatus';
import styles from './MarketOverviewPage.module.css';
import { HttpError } from '@/api/http';
import { useMemo} from 'react';


type RangeKey = '1M' | '1Y' | '5Y' | 'ALL';

const INITIAL_SYMBOLS = ['SPY', 'AAPL', 'MSFT'];

const RANGE_DAYS: Record<RangeKey, number | 'ALL'> = {
  '1M': 30,
  '1Y': 365,
  '5Y': 365 * 5,
  ALL: 'ALL',
};

/**
 * 市场总览页（阶段 0）：
 *  - 上方：ticker 多选 + 时间范围 + SPY 基准
 *  - 中部：对比图表（基期 100）
 *  - 下方：最新数据日、当日收益、宽度、任务状态
 *
 * 这是第一次完整 useState + useEffect 切片。
 */
export const MarketOverviewPage = () => {
  const { t } = useTranslation();
  // —— 视图状态（已由我实现）——
  const [symbols, setSymbols] = useState<string[]>(INITIAL_SYMBOLS);
  const [range, setRange] = useState<RangeKey>('1Y');
  const [tickerDraft, setTickerDraft] = useState('');
  
  // —— 数据状态（effect 留给你实现）——
  const [seriesState, setSeriesState] = useState<AsyncState<SeriesResponse>>({ status: 'idle' });
  const [latestTradeDate, setLatestTradeDate] = useState<string | null>(null);
  const [overview, setOverview] = useState<MarketOverview | null>(null);
  const [taskStatus, setTaskStatus] = useState<{ label: string; color: string } | null>(null);
  // —— TODO(USER_LEARNING): 数据拉取 effect —— //
  //   目标：当 symbols 或 range 变化时，发起 fetchSeries 并写入 seriesState；
  //   异步状态依次经历 loading → success | error；
  //   必须处理：
  //     ① 组件卸载或依赖变化时，取消未完成请求（AbortController）；
  //     ② 错误时写入 ApiError 而不是裸 throw；
  //     ③ 清理函数避免 setState on unmounted component。
  //   提示：使用 useEffect + AbortController；fetchSeries 的 signal 参数可用。
    
  const query= useMemo<SeriesQuery|null> (() => {
    if (latestTradeDate === null) return null;
    const endDate = latestTradeDate;
    const end = new Date(`${latestTradeDate}T00:00:00Z`);
    const days = RANGE_DAYS[range];
    if (days === 'ALL') return { symbols, startDate: '2015-01-01', endDate: endDate, normalize: true };
    const start = new Date(end.getTime() - days * 86400_000).toISOString().slice(0,10);
    return { symbols, startDate: start, endDate: endDate, normalize: true };
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
      if (error instanceof DOMException && error.name === 'AbortError') {
        return;
      }

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
}, [latestTradeDate, symbols, range, query]);

  useEffect(() => {
    const controller = new AbortController();
    fetchLatestMarketDate().then((data) => {
      setLatestTradeDate(data.latestTradeDate);
    });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetchMarketOverview(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setOverview(data);
      })
      .catch(() => {
        if (!controller.signal.aborted) setOverview(null);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetchWorkflows(controller.signal)
      .then((dags) => {
        if (controller.signal.aborted) return;
        const runs = dags
          .flatMap((dag) => dag.recentRuns ?? [])
          .filter((run) => run.startDate !== null)
          .sort((a, b) => (b.startDate! > a.startDate! ? 1 : -1));
        const latest = runs[0];
        setTaskStatus(
          latest
            ? { label: stateLabel(latest.state), color: stateColor(latest.state) }
            : null,
        );
      })
      .catch(() => {
        if (!controller.signal.aborted) setTaskStatus(null);
      });
    return () => controller.abort();
  }, []);


  const handleAddTicker = (): void => {
    const t = tickerDraft.trim().toUpperCase();
    if (!t || symbols.includes(t)) return;
    setSymbols([...symbols, t]);
    setTickerDraft('');
  };

  const handleRemoveTicker = (sym: string): void => {
    setSymbols(symbols.filter((s) => s !== sym));
  };

  const spyDailyReturn = (()=>{
    if(seriesState.status !== 'success') return null;
    const spySeries = seriesState.data.series.find((series) => series.symbol === 'SPY',
  );
  const latestPoint = spySeries?.points.at(-1);
  const previousPoint = spySeries?.points.at(-2);

  if (latestPoint === undefined || previousPoint ===undefined || previousPoint.value === 0){return null;}
  return (latestPoint.value / previousPoint.value - 1) * 100;
  })();

  const spyDailyReturnLabel = spyDailyReturn ===null ? '-' : `${spyDailyReturn >= 0? '+' :  '' }${spyDailyReturn.toFixed(2)}%`;


  return (
    <div className={styles.page}>
      <PageHeader
        title={t('market.title')}
        subtitle={t('market.subtitle')}
        actions={
          <div className={styles.rangeGroup}>
            {(['1M', '1Y', '5Y', 'ALL'] as RangeKey[]).map((r) => (
              <button
                key={r}
                className={range === r ? styles.rangeActive : styles.range}
                onClick={() => setRange(r)}
              >
                {r}
              </button>
            ))}
          </div>
        }
      />

      <Card title={t('market.compareCard')}>
        <div className={styles.tickerRow}>
          {symbols.map((s) => (
            <span key={s} className={styles.chip}>
              {s}
              <button
                className={styles.chipX}
                onClick={() => handleRemoveTicker(s)}
                aria-label={t('market.removeTicker', { symbol: s })}
              >
                ×
              </button>
            </span>
          ))}
          <div className={styles.addTicker}>
            <input
              placeholder={t('market.addTickerPlaceholder')}
              value={tickerDraft}
              onChange={(e) => setTickerDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleAddTicker();
              }}
            />
            <button onClick={handleAddTicker}>{t('market.add')}</button>
          </div>
        </div>

        <div className={styles.chartWrap}>
          <AsyncBoundary
            state={seriesState}
            isEmpty={(d) => d.series.length === 0}
            onRetry={() => setRange(range)} // 触发 effect 重跑
            emptyTitle={t('market.emptyTitle')}
            emptyHint={t('market.rangeHint', { start: query?.startDate ?? '-', end: query?.endDate ?? '-' })}
          >
            {(data) => (
              <SeriesChart
                series={data.series}
                height={360}
                onReset={() => {
                  setSymbols(INITIAL_SYMBOLS);
                  setRange('1Y');
                }}
              />
            )}
          </AsyncBoundary>
        </div>
      </Card>

      <section className={styles.kpis}>
        <Kpi label={t('market.kpi.latestDate')} value={latestTradeDate ?? '-'} />
        <Kpi label={t('market.kpi.dailyReturn')} value={spyDailyReturnLabel} tone="muted" />
        <Kpi
          label={t('market.kpi.advancers')}
          value={overview ? `${overview.advancers} / ${overview.total}` : '-'}
          tone="muted"
        />
        <Kpi
          label={t('market.kpi.breadth')}
          value={overview ? `${(overview.breadth * 100).toFixed(1)}%` : '-'}
          tone="muted"
        />
        <Kpi
          label={t('market.kpi.taskStatus')}
          value={taskStatus ? taskStatus.label : '尚未运行'}
          valueColor={taskStatus?.color}
          tone="muted"
        />
      </section>
    </div>
  );
};

const Kpi = ({
  label,
  value,
  hint,
  tone,
  valueColor,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: 'muted';
  valueColor?: string | undefined;
}) => {
  return (
    <div className={styles.kpi}>
      <div className={styles.kpiLabel}>{label}</div>
      <div
        className={tone === 'muted' ? styles.kpiValueMuted : styles.kpiValue}
        style={valueColor ? { color: valueColor } : undefined}
      >
        {value}
      </div>
      {hint ? <div className={styles.kpiHint}>{hint}</div> : null}
    </div>
  );
};

// 抑制未使用变量告警；这些会在阶段 2 真正接入 fetch 时被使用
void ({} as ApiError);

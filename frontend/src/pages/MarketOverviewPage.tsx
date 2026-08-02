import { useEffect, useState } from 'react';
import { PageHeader } from '@/components/common/PageHeader';
import { Card } from '@/components/common/Card';
import { AsyncBoundary } from '@/components/common/AsyncBoundary';
import { SeriesChart } from '@/components/chart/SeriesChart';
import { fetchSeries , fetchLatestMarketDate} from '@/api/client/market';
import type { AsyncState, ApiError } from '@/types/api';
import type { SeriesQuery, SeriesResponse } from '@/types/market';
import styles from './MarketOverviewPage.module.css';
import { HttpError } from '@/api/http';
import { useMemo} from 'react';
import { symbol } from 'zod/v4';


type RangeKey = '1M' | '1Y' | '5Y' | 'ALL';

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
  // —— 视图状态（已由我实现）——
  const [symbols, setSymbols] = useState<string[]>(['SPY', 'AAPL', 'MSFT']);
  const [range, setRange] = useState<RangeKey>('1Y');
  const [tickerDraft, setTickerDraft] = useState('');
  
  // —— 数据状态（effect 留给你实现）——
  const [seriesState, setSeriesState] = useState<AsyncState<SeriesResponse>>({ status: 'idle' });
  const [latestTradeDate, setLatestTradeDate] = useState<string | null>(null);
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
  }, [latestTradeDate, symbol, range]);

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
          title: '网络请求失败',
          detail: '请确认后端服务正在运行。',
          status: 0,
        },
      });
    });

  return () => controller.abort();
}, [latestTradeDate, symbols, range]);
  
  useEffect(() => {fetchLatestMarketDate().then((data)=>{setLatestTradeDate(data.latestTradeDate);});},[])


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
        title="市场总览"
        subtitle="S&P 500 行情比较 · 自由查看，不展示正式调仓"
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

      <Card title="对比组合">
        <div className={styles.tickerRow}>
          {symbols.map((s) => (
            <span key={s} className={styles.chip}>
              {s}
              <button
                className={styles.chipX}
                onClick={() => handleRemoveTicker(s)}
                aria-label={`移除 ${s}`}
              >
                ×
              </button>
            </span>
          ))}
          <div className={styles.addTicker}>
            <input
              placeholder="添加 ticker"
              value={tickerDraft}
              onChange={(e) => setTickerDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleAddTicker();
              }}
            />
            <button onClick={handleAddTicker}>添加</button>
          </div>
        </div>

        <div className={styles.chartWrap}>
          <AsyncBoundary
            state={seriesState}
            isEmpty={(d) => d.series.length === 0}
            onRetry={() => setRange(range)} // 触发 effect 重跑
            emptyTitle="暂无行情数据"
            emptyHint={`区间 ${query?.startDate?? '-'} → ${query?.endDate ?? '-'}`}
          >
            {(data) => <SeriesChart series={data.series} height={360} />}
          </AsyncBoundary>
        </div>
      </Card>

      <section className={styles.kpis}>
        <Kpi label="最新数据日" value={latestTradeDate ?? '-'} />
        <Kpi label="当日收益 (SPY)" value={spyDailyReturnLabel} tone="muted" />
        <Kpi label="上涨家数" value="—" tone="muted" />
        <Kpi label="市场宽度" value="—" tone="muted" />
        <Kpi label="最新任务状态" value="IDLE" tone="muted" />
      </section>
    </div>
  );
};

const Kpi = ({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: 'muted';
}) => {
  return (
    <div className={styles.kpi}>
      <div className={styles.kpiLabel}>{label}</div>
      <div className={tone === 'muted' ? styles.kpiValueMuted : styles.kpiValue}>{value}</div>
      {hint ? <div className={styles.kpiHint}>{hint}</div> : null}
    </div>
  );
};

// 抑制未使用变量告警；这些会在阶段 2 真正接入 fetch 时被使用
void ({} as ApiError);

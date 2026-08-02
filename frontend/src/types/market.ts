import type { DateRange, Frequency } from './api';
import {http} from '@/api/http';
/** Ticker 元信息 */
export interface Ticker {
  symbol: string;
  name: string;
  exchange: 'NASDAQ' | 'NYSE' | 'SP500';
  sector?: string;
  /** 是否在 S&P 500 当前成分股中 */
  inSp500: boolean;
}

/** 单点行情 */
export interface Bar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

/** 时间序列：用于画图 */
export interface SeriesPoint {
  date: string;
  /** 归一化后值，基期=100；或原始 close，由调用方决定 */
  value: number;
}

/** 多 ticker 比较接口的响应 */
export interface SeriesResponse {
  baseDate: string; // 归一化基准日
  series: Array<{
    symbol: string;
    points: SeriesPoint[];
  }>;
}

/** 查询参数：GET /market/series */
export interface SeriesQuery extends DateRange {
  symbols: string[]; // 多 ticker
  frequency?: Frequency;
  /** 是否返回归一化到 100 的结果（默认 true） */
  normalize?: boolean;
}

export function fetchSeries(
  query: SeriesQuery,
  signal?: AbortSignal,
): Promise<SeriesResponse> {
  return http<SeriesResponse>(
    '/api/v1/market/series',
    {
      query: {
        symbols: query.symbols,
        startDate: query.startDate,
        endDate: query.endDate,
        frequency: query.frequency,
        normalize: query.normalize,
      },
      signal,
    },
  );
}

export interface MarketLatestDateResponse{
  latestTradeDate : string;
}
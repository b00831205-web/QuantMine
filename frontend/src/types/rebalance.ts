import type { Page, Unit } from './api';

export interface RebalanceSummary {
  rebalanceId: string;
  backtestJob: string;
  variant: string;
  /**
   * 加权方式（`equal` / `mcap`）。必须显示：两个 job 可以共用同一个 variant，
   * 不显示它的话，同日期同因子同分位的两行看起来一模一样，权重却完全不同。
   */
  weighting?: string;
  factor: string;
  holdingPeriod: number; // 交易日
  type: 'quantile' | 'long_short';
  quantile: string; // LS / Q1..Q5
  rebalanceDate: string;
  netReturn: number; // 净收益，单位见 unit
  spyReturn: number;
  excessReturn: number;
  turnover: number;
  holdingsCount: number;
  tradingDaysToNext: number;
  unit: Unit;
}

export interface RebalanceDetail extends RebalanceSummary {
  asOfDate: string;
  holdings: Array<{ symbol: string; weight: number; quantile?: string }>;
  contributions: Array<{ symbol: string; contribution: number }>;
  /**
   * 持仓为空的原因。`long_short` 是正常的（LS 组合没有独立持仓）；
   * `artifact_missing` 是故障（回测产物 parquet 找不到，通常是 webapi 没挂 data 目录）。
   * 旧后端不返回该字段，故为可选。
   */
  holdingsStatus?: 'ok' | 'long_short' | 'artifact_missing' | 'empty';
}

export interface RebalanceQuery {
  backtestJob?: string;
  variant?: string;
  factor?: string;
  tradeDate?: string; // YYYY-MM-DD，按调仓日期搜索
  page?: number;
  pageSize?: number;
}

export type RebalancePage = Page<RebalanceSummary>;

export interface ResearchRunOption{
  runId: number;
  createdAt: string;
}

export interface ResearchFilterOptions{
  defaultRunId: number | null;
  runs: ResearchRunOption[];
  variants: string[];
  testIds: string[];
  sampleScopes: Array<'train'|'test'>;
}

export interface FactorResultRow{
  factorName: string;
  period: number;
  variantName: string;
  testId: string;
  sampleScope: 'train' | 'test';
  icMean: number| null;
  icStd: number | null;
  ir: number | null;
  n : number | null;
  tStat: number | null;
  pValue: number | null;
  significant: boolean | null;
  bhSignificant: boolean | null;
}

export type FactorResultPage = Page<FactorResultRow>;

export interface FactorResultsQuery{
  runId: number;
  variant?:string;
  testId?:string;
  sampleScope?:'train' | 'test';
  factorName?: string;
  period?:number;
  page: number;
  pageSize: number;
}

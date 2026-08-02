import type { Page, Unit } from './api';

export interface RebalanceSummary {
  rebalanceId: string;
  backtestJob: string;
  variant: string;
  factor: string;
  holdingPeriod: number; // 交易日
  type: 'quantile' | 'long_short';
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
  holdings: Array<{ symbol: string; weight: number }>;
  contributions: Array<{ symbol: string; contribution: number }>;
}

export interface RebalanceQuery {
  backtestJob?: string;
  variant?: string;
  factor?: string;
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

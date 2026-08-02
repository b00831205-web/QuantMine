import type { Page } from './api';
import type { SeriesResponse, SeriesPoint } from './market'

export interface ResearchRun {
  runId: string;
  variant: string;
  sampleScope: string;
  airflowBatch: string;
  configSnapshot: string; // hash
  gitCommit: string;
  createdAt: string;
}

export interface TestSummary {
  testId: string;
  factor: string;
  icMean: number;
  icStd: number;
  ir: number;
  sampleSize: number;
  tStat: number;
  pValue: number;
  bhSignificant: boolean;
}

export interface BacktestSummary {
  backtestJob: string;
  factor: string;
  period: number;
  quantileReturns: Record<string, number>;
  longShortReturn: number;
  sharpe: number;
  maxDrawdown: number;
  turnover: number;
  netReturn: boolean; // 是否扣除交易成本
}

export interface ResearchQuery {
  variant?: string;
  factor?: string;
  page?: number;
  pageSize?: number;
}

export type TestPage = Page<TestSummary>;
export type BacktestPage = Page<BacktestSummary>;

export interface ResearchRunOption{
  runId: number;
  createdAt: string;
}

export interface ResearchFilterOptions{
  defaultRunId: number | null;
  runs: ResearchRunOption[];
  variants: string[];
  testIds: string[];
  sampleScopes: Array<'train'|'test'>
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

export type FactorResultPage = Page<FactorResultRow>

export interface BacktestSummaryCard{
  variantName: string;
  backtestId: string;
  testId: string;
  factorName: string;
  period: number;
  quantileYearlyReturns: Record<string, number>;
  sharpe: number|null;
  maxDrawdown: number | null;
  winRate: number|null;
}

export interface BacktestSummariesQuery{
  runId: number,
  variant?: string;
  testId?:string;
  factorName?:string;
  period?: number;
  page: number;
  pageSize:number;
}

export type BacktestSummaryPage = Page<BacktestSummaryCard>

export interface BacktestSeriesQuery{
  runId: number;
  variant: string;
  backtestId: string;
  testId: string;
  factorName: string;
  period: number;
}

export type BacktestSeriesResponse = SeriesResponse;

export interface IcSeriesQuery{
  runId:number;
  variant: string;
  sampleScope: 'train'|'test';
  factorName: string;
  period: number;
}

export interface IcSeriesResponse{
  baseDate: string| null;
  series: Array<{
    symbol: string;
    points: SeriesPoint[];
  }>;
}
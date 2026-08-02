import type { FactorResultPage, ResearchFilterOptions , FactorResultsQuery, BacktestSeriesQuery} from '@/types/research';
import {http} from '@/api/http'
import type { BacktestSummariesQuery, BacktestSummaryPage, BacktestSeriesResponse} from '@/types/research';
import type { IcSeriesQuery, IcSeriesResponse } from '@/types/research';

export function fetchResearchOptions(
  runId?: number,
  signal?: AbortSignal,
): Promise<ResearchFilterOptions> {
  return http<ResearchFilterOptions>(
    '/api/v1/research/options',
    {
      query: runId === undefined ? {} : { runId },
      signal,
    },
  );
}

export function fetchFactorResults(
  query: FactorResultsQuery,
  signal?: AbortSignal,
): Promise<FactorResultPage> {
  return http<FactorResultPage>(
    '/api/v1/research/factors',
    {
      query: {
        runId: query.runId,
        variant: query.variant,
        testId: query.testId,
        sampleScope: query.sampleScope,
        factorName: query.factorName,
        period: query.period,
        page: query.page,
        pageSize: query.pageSize,
      },
      signal,
    },
  );
}

export function fetchBacktestSummaries(
  query: BacktestSummariesQuery,
  signal?: AbortSignal,
): Promise<BacktestSummaryPage>{
  return http<BacktestSummaryPage>(
    '/api/v1/research/backtest-summaries',
    {query:{
      runId: query.runId,
      variant : query.variant,
      testId: query.testId,
      factorName: query.factorName,
      period: query.period,
      page: query.page,
      pageSize: query.pageSize,
    },
    signal,}
  )
}

export function fetchBacktestSeries(
  query: BacktestSeriesQuery,
  signal?: AbortSignal,
): Promise<BacktestSeriesResponse>{
  return http<BacktestSeriesResponse>(
    '/api/v1/research/backtest-series',{
      query:{
        runId: query.runId,
        variant: query.variant,
        backtestId: query.backtestId,
        testId: query.testId,
        factorName: query.factorName,
        period: query.period
      },
      signal,
    },
  );
}

export function fetchIcSeries(
  query: IcSeriesQuery,
  signal?:AbortSignal,
): Promise<IcSeriesResponse>{
  return http<IcSeriesResponse>(
    '/api/v1/research/ic-series',
    {
      query:{
        runId: query.runId,
        variant: query.variant,
        sampleScope: query.sampleScope,
        factorName: query.factorName,
        period: query.period
      },
      signal,
    }
  )
}
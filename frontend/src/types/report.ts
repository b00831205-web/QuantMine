import type { Page } from './api';

export type ReportStatus = 'queued' | 'running' | 'success' | 'failed';

export type ReportSection =
  | 'summary'
  | 'data_quality'
  | 'methodology'
  | 'ic_significance'
  | 'stability'
  | 'backtest'
  | 'monotonicity'
  | 'risk'
  | 'appendix';

export interface ReportJob {
  reportId: string;
  researchRunId: string;
  variants: string[];
  tests: string[];
  backtestJobs: string[];
  sections: ReportSection[];
  status: ReportStatus;
  createdAt: string;
  finishedAt: string | null;
  downloadUrl: string | null;
  errorMessage: string | null;
}

export type ReportPage = Page<ReportJob>;

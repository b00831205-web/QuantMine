import type { Page } from './api';

export type ReportLang = 'zh' | 'en';

/** 同步报告接口（report.pdf / report.xlsx）的查询参数 */
export interface ReportQuery {
  runId: number;
  testId?: string;
  lang: ReportLang;
  ai: boolean;
}

/** 报告历史记录（轻量版：同步生成，生成即完成） */
export interface ReportHistoryItem {
  reportId: string;
  runId: number;
  testId?: string;
  lang: ReportLang;
  ai: boolean;
  createdAt: string;
  status: 'ready' | 'failed';
}

export type ReportHistoryPage = Page<ReportHistoryItem>;
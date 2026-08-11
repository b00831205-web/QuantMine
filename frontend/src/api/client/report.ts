import { http } from '@/api/http';
import type { ReportHistoryPage, ReportQuery } from '@/types/report';

export function buildReportPdfUrl(query: ReportQuery, inline = false): string {
  const params = new URLSearchParams({
    runId: String(query.runId),
    lang: query.lang,
    ai: String(query.ai),
    ...(query.testId ? { testId: query.testId } : {}),
    ...(query.refresh ? { refresh: '1' } : {}),
    ...(inline ? { inline: '1' } : {}),
  });
  return `/api/v1/research/report.pdf?${params}`;
}

export function buildReportXlsxUrl(query: ReportQuery): string {
  const params = new URLSearchParams({
    runId: String(query.runId),
    lang: query.lang,
    ai: String(query.ai),
    ...(query.testId ? { testId: query.testId } : {}),
  });
  return `/api/v1/research/report.xlsx?${params}`;
}

export function buildReportHistoryFileUrl(reportId: string, inline = false): string {
  const params = new URLSearchParams(inline ? { inline: 'true' } : {});
  const query = params.toString();
  return `/api/v1/reports/${encodeURIComponent(reportId)}/file${query ? `?${query}` : ''}`;
}

export function fetchReportHistory(
  runId: number,
  page: number,
  pageSize: number,
  signal?: AbortSignal,
): Promise<ReportHistoryPage> {
  return http<ReportHistoryPage>('/api/v1/reports', {
    query: { runId, page, pageSize },
    signal,
  });
}

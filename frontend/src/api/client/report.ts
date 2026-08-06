import {http} from '@/api/http';
import type {ReportHistoryPage, ReportQuery} from '@/types/report';

export function buildReportPdfUrl(query: ReportQuery, inline = false): string{
    const params = new URLSearchParams({
        runId: String(query.runId),
        lang: query.lang,
        ai: String(query.ai),
        ...(query.testId? {testId: query.testId}: {}),
        ...(inline? {inline: '1'}:{}),
    });
    return `/api/v1/research/report.pdf?${params}`;
}

export function buildReportXlsxUrl(query: ReportQuery): string{
    const params = new URLSearchParams({
        runId: String(query.runId),
        lang: query.lang,
        ai: String(query.ai),
        ...(query.testId? {testId: query.testId}: {}),
    });
    return `/api/v1/research/report.xlsx?${params}`;
}

export function fetchReportHistory(
    page: number,
    pageSize: number,
    signal?: AbortSignal,
): Promise<ReportHistoryPage>{
    return http<ReportHistoryPage>(
        '/api/v1/reports',
        {query: {page, pageSize},
    signal}
    )
}

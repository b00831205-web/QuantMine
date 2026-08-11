import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

const apiMocks = vi.hoisted(() => ({
  fetchResearchOptions: vi.fn(),
  fetchFactorResults: vi.fn(),
  fetchBacktestSummaries: vi.fn(),
}));

const reportMocks = vi.hoisted(() => ({
  fetchReportHistory: vi.fn(),
  buildReportHistoryFileUrl: vi.fn(
    (reportId: string, inline = false) => `/api/v1/reports/${reportId}/file?inline=${inline}`,
  ),
  buildReportPdfUrl: vi.fn(
    (query: { runId: number; lang: string; ai: boolean; refresh?: boolean }, inline = false) =>
      `/api/v1/research/report.pdf?runId=${query.runId}&lang=${query.lang}&ai=${query.ai}&refresh=${query.refresh ?? false}&inline=${inline}`,
  ),
  buildReportXlsxUrl: vi.fn(() => '/api/v1/research/report.xlsx'),
}));

vi.mock('@/api/client', () => apiMocks);
vi.mock('@/api/client/report', () => reportMocks);

import { ReportsPage } from './ReportsPage';

const run2Reports = {
  items: [
    {
      reportId: 'report-new',
      runId: 2,
      testId: null,
      lang: 'en',
      ai: false,
      artifactType: 'pdf',
      artifactAvailable: true,
      artifactSize: 2048,
      dataAvailable: false,
      createdAt: '2026-08-11T10:00:00Z',
      status: 'ready',
    },
    {
      reportId: 'report-old',
      runId: 2,
      testId: null,
      lang: 'zh',
      ai: true,
      artifactType: 'pdf',
      artifactAvailable: true,
      artifactSize: 1024,
      dataAvailable: false,
      createdAt: '2026-08-10T10:00:00Z',
      status: 'ready',
    },
  ],
  total: 2,
  page: 1,
  pageSize: 10,
};

const readyRegenerableReport = {
  ...run2Reports.items[0],
  dataAvailable: true,
};

afterEach(() => {
  vi.clearAllMocks();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('ReportsPage Run and history hierarchy', () => {
  it('filters history by Run, previews the selected history row, and keeps Run selectable', async () => {
    apiMocks.fetchResearchOptions.mockResolvedValue({
      defaultRunId: 2,
      runs: [
        { runId: 2, createdAt: '2026-08-11T10:00:00Z' },
        { runId: 1, createdAt: '2026-08-10T10:00:00Z' },
      ],
      variants: [],
      testIds: [],
      sampleScopes: [],
    });
    apiMocks.fetchFactorResults.mockImplementation((query: { runId: number }) =>
      Promise.resolve({ items: [], total: query.runId === 1 ? 45 : 0, page: 1, pageSize: 1 }),
    );
    apiMocks.fetchBacktestSummaries.mockImplementation((query: { runId: number }) =>
      Promise.resolve({ items: [], total: query.runId === 1 ? 6 : 0, page: 1, pageSize: 1 }),
    );
    reportMocks.fetchReportHistory.mockImplementation((runId: number) =>
      Promise.resolve(runId === 2 ? run2Reports : { items: [], total: 0, page: 1, pageSize: 10 }),
    );
    const generateFetch = vi.fn().mockResolvedValue(
      new Response(new Uint8Array([37, 80, 68, 70]), {
        status: 200,
        headers: { 'Content-Type': 'application/pdf' },
      }),
    );
    vi.stubGlobal('fetch', generateFetch);

    render(
      <MemoryRouter>
        <ReportsPage />
      </MemoryRouter>,
    );

    const newestRow = (await screen.findByText('report-new')).closest('tr');
    expect(newestRow).toHaveAttribute('aria-selected', 'true');
    expect(reportMocks.fetchReportHistory).toHaveBeenCalledWith(2, 1, 10, expect.any(AbortSignal));
    expect(document.querySelector('iframe')).toHaveAttribute(
      'src',
      '/api/v1/reports/report-new/file?inline=true',
    );

    const olderRow = screen.getByText('report-old').closest('tr');
    fireEvent.click(olderRow!);
    expect(olderRow).toHaveAttribute('aria-selected', 'true');
    expect(newestRow).toHaveAttribute('aria-selected', 'false');
    expect(document.querySelector('iframe')).toHaveAttribute(
      'src',
      '/api/v1/reports/report-old/file?inline=true',
    );

    const runSelect = document.querySelector<HTMLSelectElement>('#report-run');
    fireEvent.change(runSelect!, { target: { value: '1' } });

    await waitFor(() => {
      expect(runSelect).toHaveValue('1');
      expect(reportMocks.fetchReportHistory).toHaveBeenCalledWith(
        1,
        1,
        10,
        expect.any(AbortSignal),
      );
    });
    expect(document.querySelector('iframe')).not.toBeInTheDocument();

    const generateButton = document.querySelector<HTMLButtonElement>('#generate-report-button');
    await waitFor(() => expect(generateButton).toBeEnabled());
    const aiToggle = document.querySelector<HTMLButtonElement>('#report-ai-toggle');
    expect(aiToggle).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(aiToggle!);
    expect(aiToggle).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(generateButton!);

    await waitFor(() => {
      expect(reportMocks.buildReportPdfUrl).toHaveBeenCalledWith(
        { runId: 1, lang: 'zh', ai: true, refresh: true },
        true,
      );
      expect(generateFetch).toHaveBeenCalledWith(expect.stringContaining('runId=1'), {
        credentials: 'include',
      });
    });
  });

  it('regenerates the selected report with the current AI and language controls', async () => {
    apiMocks.fetchResearchOptions.mockResolvedValue({
      defaultRunId: 2,
      runs: [{ runId: 2, createdAt: '2026-08-11T10:00:00Z' }],
      variants: [],
      testIds: [],
      sampleScopes: [],
    });
    apiMocks.fetchFactorResults.mockResolvedValue({
      items: [],
      total: 1,
      page: 1,
      pageSize: 1,
    });
    apiMocks.fetchBacktestSummaries.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      pageSize: 1,
    });
    reportMocks.fetchReportHistory.mockResolvedValue({
      items: [readyRegenerableReport],
      total: 1,
      page: 1,
      pageSize: 10,
    });
    const regenerateFetch = vi.fn().mockResolvedValue(
      new Response(new Uint8Array([37, 80, 68, 70]), {
        status: 200,
        headers: { 'Content-Type': 'application/pdf' },
      }),
    );
    vi.stubGlobal('fetch', regenerateFetch);

    render(
      <MemoryRouter initialEntries={['/reports?runId=2&lang=en']}>
        <ReportsPage />
      </MemoryRouter>,
    );

    await screen.findByText('report-new');
    fireEvent.click(document.querySelector<HTMLButtonElement>('#report-ai-toggle')!);
    fireEvent.click(document.querySelector<HTMLButtonElement>('#report-regenerate-button')!);

    await waitFor(() => {
      expect(reportMocks.buildReportPdfUrl).toHaveBeenCalledWith(
        { runId: 2, lang: 'en', ai: true, refresh: true },
        true,
      );
    });
  });
});

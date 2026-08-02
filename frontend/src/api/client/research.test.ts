import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  fetchBacktestSummaries,
  fetchBacktestSeries,
  fetchFactorResults,
  fetchIcSeries,
  fetchResearchOptions,
} from './research';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('research API client', () => {
  it('loads the research filter options endpoint', async () => {
    const payload = {
      defaultRunId: 42,
      runs: [{ runId: 42, createdAt: '2026-07-30T09:00:00' }],
      variants: ['raw'],
      testIds: ['newey_raw'],
      sampleScopes: ['train', 'test'],
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(payload), { status: 200 }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(fetchResearchOptions()).resolves.toEqual(payload);

    const requestedUrl = new URL(String(fetchMock.mock.calls[0]?.[0]));
    expect(requestedUrl.pathname).toBe('/api/v1/research/options');
    expect(requestedUrl.search).toBe('');
  });

  it('serializes runId when loading filter options for a selected run', async () => {
    const payload = {
      defaultRunId: 42,
      runs: [{ runId: 42, createdAt: '2026-07-30T09:00:00' }],
      variants: ['orthogonalized'],
      testIds: ['newey_orthogonalized'],
      sampleScopes: ['test'],
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(payload), { status: 200 }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(fetchResearchOptions(41)).resolves.toEqual(payload);

    const requestedUrl = new URL(String(fetchMock.mock.calls[0]?.[0]));
    expect(requestedUrl.pathname).toBe('/api/v1/research/options');
    expect(requestedUrl.searchParams.get('runId')).toBe('41');
  });

  it('serializes factor-result filters and omits unspecified filters', async () => {
    const payload = { items: [], total: 0, page: 2, pageSize: 25 };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(payload), { status: 200 }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(
      fetchFactorResults({
        runId: 42,
        variant: 'raw',
        page: 2,
        pageSize: 25,
      }),
    ).resolves.toEqual(payload);

    const requestedUrl = new URL(String(fetchMock.mock.calls[0]?.[0]));
    expect(requestedUrl.pathname).toBe('/api/v1/research/factors');
    expect(requestedUrl.searchParams.get('runId')).toBe('42');
    expect(requestedUrl.searchParams.get('variant')).toBe('raw');
    expect(requestedUrl.searchParams.get('page')).toBe('2');
    expect(requestedUrl.searchParams.get('pageSize')).toBe('25');
    expect(requestedUrl.searchParams.has('testId')).toBe(false);
    expect(requestedUrl.searchParams.has('factorName')).toBe(false);
  });

  it('serializes backtest-summary filters and omits unspecified filters', async () => {
    const payload = { items: [], total: 0, page: 1, pageSize: 25 };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(payload), { status: 200 }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(
      fetchBacktestSummaries({
        runId: 42,
        variant: 'raw',
        testId: 'newey_raw',
        page: 1,
        pageSize: 25,
      }),
    ).resolves.toEqual(payload);

    const requestedUrl = new URL(String(fetchMock.mock.calls[0]?.[0]));
    expect(requestedUrl.pathname).toBe('/api/v1/research/backtest-summaries');
    expect(requestedUrl.searchParams.get('runId')).toBe('42');
    expect(requestedUrl.searchParams.get('variant')).toBe('raw');
    expect(requestedUrl.searchParams.get('testId')).toBe('newey_raw');
    expect(requestedUrl.searchParams.get('page')).toBe('1');
    expect(requestedUrl.searchParams.get('pageSize')).toBe('25');
    expect(requestedUrl.searchParams.has('factorName')).toBe(false);
    expect(requestedUrl.searchParams.has('period')).toBe(false);
  });

  it('serializes the complete identity for a backtest net-value curve', async () => {
    const payload = { baseDate: '2024-01-02', series: [] };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(payload), { status: 200 }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(
      fetchBacktestSeries({
        runId: 10,
        variant: 'legacy_tmp_raw',
        backtestId: 'legacy_tmp_after_cost',
        testId: 'legacy_tmp_bh',
        factorName: 'Momentum',
        period: 5,
      }),
    ).resolves.toEqual(payload);

    const requestedUrl = new URL(String(fetchMock.mock.calls[0]?.[0]));
    expect(requestedUrl.pathname).toBe('/api/v1/research/backtest-series');
    expect(requestedUrl.searchParams.get('runId')).toBe('10');
    expect(requestedUrl.searchParams.get('variant')).toBe('legacy_tmp_raw');
    expect(requestedUrl.searchParams.get('backtestId')).toBe('legacy_tmp_after_cost');
    expect(requestedUrl.searchParams.get('testId')).toBe('legacy_tmp_bh');
    expect(requestedUrl.searchParams.get('factorName')).toBe('Momentum');
    expect(requestedUrl.searchParams.get('period')).toBe('5');
  });

  it('serializes the selected IC artifact identity', async () => {
    const payload = { baseDate: '2024-01-02', series: [] };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(payload), { status: 200 }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(
      fetchIcSeries({
        runId: 10,
        variant: 'legacy_tmp_raw',
        sampleScope: 'train',
        factorName: 'TwentyDayAvgVol',
        period: 5,
      }),
    ).resolves.toEqual(payload);

    const requestedUrl = new URL(String(fetchMock.mock.calls[0]?.[0]));
    expect(requestedUrl.pathname).toBe('/api/v1/research/ic-series');
    expect(requestedUrl.searchParams.get('runId')).toBe('10');
    expect(requestedUrl.searchParams.get('variant')).toBe('legacy_tmp_raw');
    expect(requestedUrl.searchParams.get('sampleScope')).toBe('train');
    expect(requestedUrl.searchParams.get('factorName')).toBe('TwentyDayAvgVol');
    expect(requestedUrl.searchParams.get('period')).toBe('5');
  });
});

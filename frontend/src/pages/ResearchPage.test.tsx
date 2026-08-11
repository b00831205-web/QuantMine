import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';

const apiMocks = vi.hoisted(() => ({
  fetchBacktestSummaries: vi.fn(),
  fetchBacktestSeries: vi.fn(),
  fetchResearchOptions: vi.fn(),
  fetchFactorResults: vi.fn(),
}));

vi.mock('@/api/client', () => apiMocks);

import { ResearchPage } from './ResearchPage';

const LocationProbe = () => {
  const location = useLocation();
  return <output data-testid="location">{`${location.pathname}${location.search}`}</output>;
};

afterEach(() => {
  vi.clearAllMocks();
  apiMocks.fetchBacktestSummaries.mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    pageSize: 25,
  });
});

describe('ResearchPage', () => {
  it('loads factor results for the backend-selected default run', async () => {
    apiMocks.fetchResearchOptions.mockResolvedValue({
      defaultRunId: 42,
      runs: [{ runId: 42, createdAt: '2026-07-30T09:00:00' }],
      variants: ['raw'],
      testIds: ['newey_raw'],
      sampleScopes: ['train', 'test'],
    });
    apiMocks.fetchFactorResults.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      pageSize: 25,
    });
    apiMocks.fetchBacktestSummaries.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      pageSize: 25,
    });

    render(
      <MemoryRouter>
        <ResearchPage />
      </MemoryRouter>,
    );

    expect(await screen.findByRole('option', { name: /Run 42/ })).toBeInTheDocument();

    await waitFor(() => {
      expect(apiMocks.fetchFactorResults).toHaveBeenCalledWith(
        { runId: 42, page: 1, pageSize: 25 },
        expect.any(AbortSignal),
      );
      expect(apiMocks.fetchBacktestSummaries).toHaveBeenCalledWith(
        { runId: 42, page: 1, pageSize: 25 },
        expect.any(AbortSignal),
      );
    });
  });

  it('opens factor detail with the complete row identity after double-clicking a factor row', async () => {
    apiMocks.fetchResearchOptions.mockResolvedValue({
      defaultRunId: 10,
      runs: [{ runId: 10, createdAt: '2026-08-01T09:00:00' }],
      variants: ['legacy_tmp_raw'],
      testIds: ['legacy_tmp_bh'],
      sampleScopes: ['train'],
    });
    apiMocks.fetchFactorResults.mockResolvedValue({
      items: [{
        factorName: 'TwentyDayAvgVol',
        period: 5,
        variantName: 'legacy_tmp_raw',
        testId: 'legacy_tmp_bh',
        sampleScope: 'train',
        icMean: 0.01,
        icStd: 0.1,
        ir: 0.1,
        n: 100,
        tStat: 1.0,
        pValue: 0.3,
        significant: false,
        bhSignificant: false,
      }],
      total: 1,
      page: 1,
      pageSize: 25,
    });
    apiMocks.fetchBacktestSummaries.mockResolvedValue({
      items: [], total: 0, page: 1, pageSize: 25,
    });

    render(
      <MemoryRouter initialEntries={['/research']}>
        <ResearchPage />
        <LocationProbe />
      </MemoryRouter>,
    );

    fireEvent.doubleClick(await screen.findByText('TwentyDayAvgVol'));

    await waitFor(() => {
      expect(screen.getByTestId('location')).toHaveTextContent(
        '/research/factors/TwentyDayAvgVol?runId=10&variant=legacy_tmp_raw&testId=legacy_tmp_bh&sampleScope=train&period=5',
      );
    });
  });

  it('requests run-specific filter options after the selected run changes', async () => {
    const options = {
      defaultRunId: 42,
      runs: [
        { runId: 42, createdAt: '2026-07-30T09:00:00' },
        { runId: 41, createdAt: '2026-07-29T09:00:00' },
      ],
      variants: ['raw'],
      testIds: ['newey_raw'],
      sampleScopes: ['train'],
    };
    apiMocks.fetchResearchOptions.mockResolvedValue(options);
    apiMocks.fetchFactorResults.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      pageSize: 25,
    });

    render(
      <MemoryRouter>
        <ResearchPage />
      </MemoryRouter>,
    );

    const runSelect = await screen.findByLabelText('Research Run');
    fireEvent.change(runSelect, { target: { value: '41' } });

    await waitFor(() => {
      expect(apiMocks.fetchResearchOptions).toHaveBeenCalledWith(
        41,
        expect.any(AbortSignal),
      );
    });
  });

  it('renders a backtest summary card returned for the active run', async () => {
    apiMocks.fetchResearchOptions.mockResolvedValue({
      defaultRunId: 42,
      runs: [{ runId: 42, createdAt: '2026-07-30T09:00:00' }],
      variants: ['raw'],
      testIds: ['newey_raw'],
      sampleScopes: ['train'],
    });
    apiMocks.fetchFactorResults.mockResolvedValue({
      items: [], total: 0, page: 1, pageSize: 25,
    });
    apiMocks.fetchBacktestSummaries.mockResolvedValue({
      items: [{
        variantName: 'raw',
        backtestId: 'raw_test',
        testId: 'newey_raw',
        factorName: 'momentum_20d',
        period: 5,
        quantileYearlyReturns: { Q1: -0.02, Q5: 0.11, longShort: 0.13 },
        sharpe: 1.2,
        maxDrawdown: -0.08,
        winRate: 0.55,
      }],
      total: 1,
      page: 1,
      pageSize: 25,
    });

    render(
      <MemoryRouter>
        <ResearchPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText('momentum_20d')).toBeInTheDocument();
  });

  it('expands one card and requests its net-value curve', async () => {
    apiMocks.fetchResearchOptions.mockResolvedValue({
      defaultRunId: 42,
      runs: [{ runId: 42, createdAt: '2026-07-30T09:00:00' }],
      variants: ['raw'],
      testIds: ['newey_raw'],
      sampleScopes: ['train'],
    });
    apiMocks.fetchFactorResults.mockResolvedValue({
      items: [], total: 0, page: 1, pageSize: 25,
    });
    apiMocks.fetchBacktestSummaries.mockResolvedValue({
      items: [{
        variantName: 'raw',
        backtestId: 'raw_test',
        testId: 'newey_raw',
        factorName: 'momentum_20d',
        period: 5,
        quantileYearlyReturns: { Q1: -0.02, Q5: 0.11, longShort: 0.13 },
        sharpe: 1.2,
        maxDrawdown: -0.08,
        winRate: 0.55,
      }],
      total: 1,
      page: 1,
      pageSize: 25,
    });
    apiMocks.fetchBacktestSeries.mockResolvedValue({
      baseDate: '2024-01-02',
      series: [],
    });

    render(
      <MemoryRouter>
        <ResearchPage />
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole('button', { name: '查看净值曲线' }));

    await waitFor(() => {
      expect(apiMocks.fetchBacktestSeries).toHaveBeenCalledWith(
        {
          runId: 42,
          variant: 'raw',
          backtestId: 'raw_test',
          testId: 'newey_raw',
          factorName: 'momentum_20d',
          period: 5,
        },
        expect.any(AbortSignal),
      );
    });
    expect(screen.getByRole('button', { name: '收起净值曲线' })).toBeInTheDocument();
    expect(screen.getByText('净值曲线 · momentum_20d · 5天')).toBeInTheDocument();
  });

  it('collapses an expanded curve when the global filters change', async () => {
    apiMocks.fetchResearchOptions.mockResolvedValue({
      defaultRunId: 42,
      runs: [{ runId: 42, createdAt: '2026-07-30T09:00:00' }],
      variants: ['raw'],
      testIds: ['newey_raw'],
      sampleScopes: ['train'],
    });
    apiMocks.fetchFactorResults.mockResolvedValue({
      items: [], total: 0, page: 1, pageSize: 25,
    });
    apiMocks.fetchBacktestSummaries.mockResolvedValue({
      items: [{
        variantName: 'raw',
        backtestId: 'raw_test',
        testId: 'newey_raw',
        factorName: 'momentum_20d',
        period: 5,
        quantileYearlyReturns: { Q1: -0.02, Q5: 0.11, longShort: 0.13 },
        sharpe: 1.2,
        maxDrawdown: -0.08,
        winRate: 0.55,
      }],
      total: 1,
      page: 1,
      pageSize: 25,
    });
    apiMocks.fetchBacktestSeries.mockResolvedValue({
      baseDate: '2024-01-02',
      series: [],
    });

    render(
      <MemoryRouter>
        <ResearchPage />
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole('button', { name: '查看净值曲线' }));
    expect(await screen.findByText('净值曲线 · momentum_20d · 5天')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Variant'), {
      target: { value: 'raw' },
    });

    await waitFor(() => {
      expect(apiMocks.fetchBacktestSummaries).toHaveBeenLastCalledWith(
        { runId: 42, variant: 'raw', page: 1, pageSize: 25 },
        expect.any(AbortSignal),
      );
    });
    await waitFor(() => {
      expect(screen.queryByText('净值曲线 · momentum_20d · 5天')).not.toBeInTheDocument();
    });
  });

  it('replaces and clears filter controls after changing run', async () => {
    const newestOptions = {
      defaultRunId: 42,
      runs: [
        { runId: 42, createdAt: '2026-07-30T09:00:00' },
        { runId: 41, createdAt: '2026-07-29T09:00:00' },
      ],
      variants: ['raw'],
      testIds: ['newey_raw'],
      sampleScopes: ['train'],
    };
    const historicalOptions = {
      ...newestOptions,
      variants: ['orthogonalized'],
      testIds: ['newey_orthogonalized'],
      sampleScopes: ['test'],
    };
    apiMocks.fetchResearchOptions
      .mockResolvedValueOnce(newestOptions)
      .mockResolvedValueOnce(newestOptions)
      .mockResolvedValueOnce(historicalOptions);
    apiMocks.fetchFactorResults.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      pageSize: 25,
    });

    render(
      <MemoryRouter>
        <ResearchPage />
      </MemoryRouter>,
    );

    const variantSelect = await screen.findByLabelText('Variant');
    await screen.findByRole('option', { name: 'raw' });
    fireEvent.change(variantSelect, { target: { value: 'raw' } });
    expect(variantSelect).toHaveValue('raw');

    fireEvent.change(screen.getByLabelText('Research Run'), {
      target: { value: '41' },
    });

    expect(variantSelect).toHaveValue('');
    expect(await screen.findByRole('option', { name: 'orthogonalized' }))
      .toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'raw' })).not.toBeInTheDocument();
  });
});

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi, beforeEach } from 'vitest';

const apiMocks = vi.hoisted(() => ({
  fetchIcSeries: vi.fn(),
  fetchResearchOptions: vi.fn(),
  fetchFactorResults: vi.fn(),
  fetchBacktestSummaries: vi.fn(),
  fetchBacktestSeries: vi.fn(),
}));

vi.mock('@/api/client/research', () => apiMocks);

vi.mock('@/components/chart/SeriesChart', () => ({
  SeriesChart: () => <div data-testid="series-chart" />,
}));
import { FactorDetailPage } from './FactorDetailPage';

afterEach(() => {
  vi.clearAllMocks();
});

beforeEach(()=>{
  apiMocks.fetchResearchOptions.mockReset();
  apiMocks.fetchResearchOptions.mockResolvedValue({
    defaultRunId: 10,
    runs: [
      { runId: 10, createdAt: '2026-07-27T02:25:33.057550' },
      { runId: 9, createdAt: '2026-07-27T02:22:09.610531' },
    ],
    variants: [],
    testIds: [],
    sampleScopes: [],
  });
  apiMocks.fetchIcSeries.mockReset();
  apiMocks.fetchIcSeries.mockResolvedValue({
    baseDate: null,
    series: [],
  });
  apiMocks.fetchFactorResults.mockReset();
  apiMocks.fetchFactorResults.mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    pageSize: 100,
  });
  apiMocks.fetchBacktestSummaries.mockReset();
  apiMocks.fetchBacktestSummaries.mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    pageSize: 25,
  });
  apiMocks.fetchBacktestSeries.mockReset();
  apiMocks.fetchBacktestSeries.mockResolvedValue({
    baseDate: null,
    series: [],
  });
})

describe('FactorDetailPage', () => {
  it('reads the selected factor period from the research-result URL', () => {
    render(
      <MemoryRouter
        initialEntries={[
          '/research/factors/TwentyDayAvgVol?runId=10&variant=legacy_tmp_raw&testId=legacy_tmp_bh&sampleScope=train&period=5',
        ]}
      >
        <Routes>
          <Route
            path="/research/factors/:factorName"
            element={<FactorDetailPage />}
          />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', { name: 'TwentyDayAvgVol' })).toBeInTheDocument();
    expect(screen.getByText('选中周期：5 天')).toBeInTheDocument();
  });

  it('loads research-run choices and selects the run encoded in the URL', async () => {
    render(
      <MemoryRouter
        initialEntries={[
          '/research/factors/TwentyDayAvgVol?runId=10&variant=legacy_tmp_raw&testId=legacy_tmp_bh&sampleScope=train&period=5',
        ]}
      >
        <Routes>
          <Route
            path="/research/factors/:factorName"
            element={<FactorDetailPage />}
          />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(apiMocks.fetchResearchOptions).toHaveBeenCalledWith(
        undefined,
        expect.any(AbortSignal),
      );
    });

    // 页面有 4 个 select（run/variant/testId/sampleScope），必须按可访问名字定位 run 选择器
    const runSelect = screen.getByRole('combobox', { name: 'Research Run' });
    await waitFor(() => {
      expect(runSelect).toHaveValue('10');
    });

    expect(screen.getByRole('option', { name: /Run 10/ })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /Run 9/ })).toBeInTheDocument();
  });

  it('clears downstream URL filters when changing the research run', async () => {
    render(
      <MemoryRouter
        initialEntries={[
          '/research/factors/TwentyDayAvgVol?runId=10&variant=legacy_tmp_raw&testId=legacy_tmp_bh&sampleScope=train&period=5',
        ]}
      >
        <Routes>
          <Route
            path="/research/factors/:factorName"
            element={<FactorDetailPage />}
          />
          <Route path="/research" element={<div>Research page</div>} />
        </Routes>
      </MemoryRouter>,
    );

    // 页面有 4 个 select，必须按可访问名字定位 run 选择器；
    // 且 options 是异步加载的，用 findByRole 等 select 渲染出来再查
    const runSelect = await screen.findByRole('combobox', { name: 'Research Run' });
    await waitFor(() => {
      expect(runSelect).toHaveValue('10');
    });

    fireEvent.change(runSelect, { target: { value: '9' } });

    await waitFor(() => {
      expect(apiMocks.fetchResearchOptions).toHaveBeenCalledWith(
        9,
        expect.any(AbortSignal),
      );
    });
  });

  it('loads the IC curve with the complete selected identity', async () => {
    apiMocks.fetchIcSeries.mockResolvedValue({
      baseDate: '2024-01-02',
      series: [{ symbol: 'IC', points: [{ date: '2024-01-02', value: 0.01 }] }],
    });

    render(
      <MemoryRouter
        initialEntries={[
          '/research/factors/TwentyDayAvgVol?runId=10&variant=legacy_tmp_raw&testId=legacy_tmp_bh&sampleScope=train&period=5',
        ]}
      >
        <Routes>
          <Route
            path="/research/factors/:factorName"
            element={<FactorDetailPage />}
          />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(apiMocks.fetchIcSeries).toHaveBeenCalledWith(
        {
          runId: 10,
          variant: 'legacy_tmp_raw',
          sampleScope: 'train',
          factorName: 'TwentyDayAvgVol',
          period: 5,
        },
        expect.any(AbortSignal),
      );
    });
  });
});

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import i18n from '@/i18n';

const marketMocks = vi.hoisted(() => ({
  fetchLatestMarketDate: vi.fn(),
  fetchSeries: vi.fn(),
  fetchMarketOverview: vi.fn(),
}));

const clientMocks = vi.hoisted(() => ({
  fetchWorkflows: vi.fn(),
}));

vi.mock('@/api/client/market', () => marketMocks);
vi.mock('@/api/client', () => clientMocks);
vi.mock('@/components/chart/SeriesChart', () => ({
  SeriesChart: ({ onReset }: { onReset?: () => void }) => (
    <button type="button" onClick={onReset}>
      reset chart
    </button>
  ),
}));

import { MarketOverviewPage } from './MarketOverviewPage';

const seriesResponse = {
  baseDate: '2026-08-07',
  series: [
    {
      symbol: 'SPY',
      points: [
        { date: '2026-08-07', value: 100 },
        { date: '2026-08-08', value: 101 },
      ],
    },
    {
      symbol: 'AAPL',
      points: [
        { date: '2026-08-07', value: 200 },
        { date: '2026-08-08', value: 202 },
      ],
    },
    {
      symbol: 'MSFT',
      points: [
        { date: '2026-08-07', value: 300 },
        { date: '2026-08-08', value: 303 },
      ],
    },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  marketMocks.fetchLatestMarketDate.mockResolvedValue({ latestTradeDate: '2026-08-08' });
  marketMocks.fetchSeries.mockResolvedValue(seriesResponse);
  marketMocks.fetchMarketOverview.mockResolvedValue({
    latestTradeDate: '2026-08-08',
    advancers: 320,
    decliners: 180,
    total: 500,
    breadth: 0.64,
  });
  clientMocks.fetchWorkflows.mockResolvedValue([
    {
      dagId: 'market-data-refresh',
      displayName: 'Market data refresh',
      isPaused: false,
      description: null,
      owners: ['quant'],
      tags: ['market'],
      scheduleSummary: 'Daily',
      nextRun: null,
      lastRun: null,
      recentRuns: [],
    },
  ]);
});

const renderPage = () => render(<MarketOverviewPage />);

describe('MarketOverviewPage', () => {
  it('exposes the selected range through pressed button semantics', async () => {
    renderPage();

    await screen.findByRole('button', { name: 'reset chart' });

    expect(screen.getByRole('button', { name: '1Y' })).toHaveAttribute('aria-pressed', 'true');

    fireEvent.click(screen.getByRole('button', { name: '1M' }));

    expect(screen.getByRole('button', { name: '1M' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('adds a trimmed ticker and removes it through its translated control', async () => {
    renderPage();

    await screen.findByRole('button', { name: 'reset chart' });

    const tickerInput = screen.getByRole('textbox');
    fireEvent.change(tickerInput, { target: { value: ' nvda ' } });
    fireEvent.keyDown(tickerInput, { key: 'Enter' });

    expect(screen.getByText('NVDA')).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', {
        name: i18n.t('market.removeTicker', { symbol: 'NVDA' }),
      }),
    );

    await screen.findByText('+1.00%');

    expect(screen.queryByText('NVDA')).not.toBeInTheDocument();
  });

  it('restores the default symbols and one-year range when the chart resets', async () => {
    renderPage();

    const tickerInput = screen.getByRole('textbox');
    fireEvent.change(tickerInput, { target: { value: 'NVDA' } });
    fireEvent.keyDown(tickerInput, { key: 'Enter' });
    fireEvent.click(screen.getByRole('button', { name: '1M' }));
    fireEvent.click(await screen.findByRole('button', { name: 'reset chart' }));
    await act(async () => undefined);

    expect(screen.queryByText('NVDA')).not.toBeInTheDocument();
    expect(screen.getByText('SPY')).toBeInTheDocument();
    expect(screen.getByText('AAPL')).toBeInTheDocument();
    expect(screen.getByText('MSFT')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '1Y' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('requests normalized series for the selected range using the latest trade date', async () => {
    renderPage();

    await waitFor(() => {
      expect(marketMocks.fetchSeries).toHaveBeenCalledWith(
        {
          symbols: ['SPY', 'AAPL', 'MSFT'],
          startDate: '2025-08-08',
          endDate: '2026-08-08',
          normalize: true,
        },
        expect.any(AbortSignal),
      );
    });

    fireEvent.click(screen.getByRole('button', { name: '1M' }));

    await waitFor(() => {
      expect(marketMocks.fetchSeries).toHaveBeenLastCalledWith(
        {
          symbols: ['SPY', 'AAPL', 'MSFT'],
          startDate: '2026-07-09',
          endDate: '2026-08-08',
          normalize: true,
        },
        expect.any(AbortSignal),
      );
    });
  });
});

/**
 * 详情页与 AppShell 缓存的交互回归测试。
 *
 * 曾经的真实 bug：AppShell 用 KeepAlive 缓存了每一个访问过的路径，详情页离开后
 * 并不卸载——它的 AbortController 清理不会执行，请求照旧返回，effect 照旧调
 * setSearchParams。而 useNavigate 在被冻结的那一帧里记住的是旧详情页的
 * pathname，于是这次“补写 period”把地址栏 replace 回了上一个因子，
 * 表现为：点进任何因子，看到的都是上一次选中的那个。
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor, act } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';

const apiMocks = vi.hoisted(() => ({
  fetchResearchOptions: vi.fn(),
  fetchFactorResults: vi.fn(),
  fetchBacktestSummaries: vi.fn(),
  fetchBacktestSeries: vi.fn(),
  fetchIcSeries: vi.fn(),
}));

vi.mock('@/api/client', async () => ({
  ...(await vi.importActual<Record<string, unknown>>('@/api/client')),
  ...apiMocks,
}));
vi.mock('@/api/client/research', async () => ({
  ...(await vi.importActual<Record<string, unknown>>('@/api/client/research')),
  ...apiMocks,
}));
vi.mock('@/components/chart/SeriesChart', () => ({
  SeriesChart: () => <div data-testid="series-chart" />,
}));

import { AppShell } from '@/components/layout/AppShell';
import { ResearchPage } from './ResearchPage';
import { FactorDetailPage } from './FactorDetailPage';

const row = (factorName: string, period: number) => ({
  factorName,
  period,
  variantName: 'raw',
  testId: 'newey_raw',
  sampleScope: 'train' as const,
  icMean: 0.01,
  icStd: 0.1,
  ir: 0.1,
  n: 100,
  tStat: 1,
  pValue: 0.3,
  significant: false,
  bhSignificant: false,
});

/** 让第一个因子的统计请求悬在半空，直到测试主动放行 */
let releaseSlowFactor: (() => void) | null = null;

beforeEach(() => {
  releaseSlowFactor = null;
  apiMocks.fetchResearchOptions.mockReset().mockResolvedValue({
    defaultRunId: 10,
    runs: [{ runId: 10, createdAt: '2026-08-01T09:00:00' }],
    variants: ['raw'],
    testIds: ['newey_raw'],
    sampleScopes: ['train'],
  });
  apiMocks.fetchFactorResults.mockReset().mockImplementation((q: { factorName?: string }) => {
    // 列表页不带 factorName，详情页带
    if (q.factorName === undefined) {
      return Promise.resolve({
        items: [row('AlphaOne', 5), row('BetaTwo', 5)],
        total: 2,
        page: 1,
        pageSize: 25,
      });
    }
    // 详情页拿到的周期与 URL 里的不同，页面必须补写一次 URL
    const answer = { items: [row(q.factorName, 20)], total: 1, page: 1, pageSize: 100 };
    if (q.factorName === 'AlphaOne') {
      return new Promise((resolve) => {
        releaseSlowFactor = () => resolve(answer);
      });
    }
    return Promise.resolve(answer);
  });
  apiMocks.fetchBacktestSummaries.mockReset().mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    pageSize: 25,
  });
  apiMocks.fetchBacktestSeries.mockReset().mockResolvedValue({ baseDate: null, series: [] });
  apiMocks.fetchIcSeries.mockReset().mockResolvedValue({ baseDate: null, series: [] });
});

const LocationProbe = () => {
  const { pathname, search } = useLocation();
  return <output data-testid="location">{`${pathname}${search}`}</output>;
};

describe('factor detail inside the app shell', () => {
  it('keeps the factor just opened when the previous one finishes loading', async () => {
    render(
      <MemoryRouter initialEntries={['/research']}>
        <Routes>
          <Route path="/" element={<AppShell />}>
            <Route path="research" element={<ResearchPage />} />
            <Route path="research/factors/:factorName" element={<FactorDetailPage />} />
          </Route>
        </Routes>
        <LocationProbe />
      </MemoryRouter>,
    );

    // 打开 AlphaOne，在它的统计返回之前就退回列表
    fireEvent.doubleClick(await screen.findByText('AlphaOne'));
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'AlphaOne' })).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole('button', { name: /返回研究结果|Back to research/ }));
    await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('/research'));

    // 再打开 BetaTwo
    fireEvent.doubleClick(await screen.findByText('BetaTwo'));
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('BetaTwo'));

    // AlphaOne 那个迟到的响应现在才落地，不能把地址栏拖回去
    await act(async () => {
      releaseSlowFactor?.();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(screen.getByTestId('location')).toHaveTextContent('/research/factors/BetaTwo');
    expect(screen.getByRole('heading', { name: 'BetaTwo' })).toBeInTheDocument();
  });
});

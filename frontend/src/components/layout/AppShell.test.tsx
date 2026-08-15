import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { AppShell } from '@/components/layout/AppShell';
import styles from '@/components/layout/AppShell.module.css';

describe('AppShell', () => {
  it('renders brand and navigation links', () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/market']}>
        <Routes>
          <Route path="/" element={<AppShell />}>
            <Route path="market" element={<div>MARKET_BODY</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );
    expect(container.textContent).toContain('QUANTMINE');
    expect(container.textContent).toContain('市场总览');
    expect(container.textContent).toContain('MARKET_BODY');
  });

  it('gives the AI workbench a fixed-height viewport', () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/ai']}>
        <Routes>
          <Route path="/" element={<AppShell />}>
            <Route path="ai" element={<div>AI_BODY</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(container.querySelector('main')).toHaveClass(styles.workbenchContent!);
    expect(container.querySelector('.ka-wrapper')).toHaveClass(styles.keepAliveFullHeight!);
    expect(container.querySelector('.ka-content')).toHaveClass(styles.keepAliveFullHeight!);
  });

  it('caches the sidebar pages but not the detail routes under them', () => {
    const routes = (
      <Route path="/" element={<AppShell />}>
        <Route path="research" element={<div>RESEARCH_BODY</div>} />
        <Route path="research/factors/:factorName" element={<div>FACTOR_BODY</div>} />
      </Route>
    );

    const cached = render(
      <MemoryRouter initialEntries={['/research']}>
        <Routes>{routes}</Routes>
      </MemoryRouter>,
    );
    expect(cached.container.querySelector('.ka-wrapper')).toBeInTheDocument();

    // 详情页留在缓存里就永不卸载，请求和 setSearchParams 会在离开后继续跑，
    // 把地址栏拖回上一个因子
    const detail = render(
      <MemoryRouter initialEntries={['/research/factors/TwentyDayAvgVol']}>
        <Routes>{routes}</Routes>
      </MemoryRouter>,
    );
    expect(detail.container.textContent).toContain('FACTOR_BODY');
    expect(detail.container.querySelector('.ka-wrapper')).not.toBeInTheDocument();
  });

  it('keeps AI Config in the normal scrollable document flow', () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/ai/config']}>
        <Routes>
          <Route path="/" element={<AppShell />}>
            <Route path="ai/config" element={<div>AI_CONFIG_BODY</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(container.querySelector('main')).not.toHaveClass(styles.workbenchContent!);
    expect(container.querySelector('.ka-wrapper')).not.toHaveClass(styles.keepAliveFullHeight!);
    expect(container.querySelector('.ka-content')).not.toHaveClass(styles.keepAliveFullHeight!);
  });
});

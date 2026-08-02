import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { AppShell } from '@/components/layout/AppShell';

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
});

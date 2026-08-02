import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AsyncBoundary } from '@/components/common/AsyncBoundary';
import type { AsyncState } from '@/types/api';

describe('AsyncBoundary', () => {
  it('renders loading view when state is loading', () => {
    const state: AsyncState<{ ok: boolean }> = { status: 'loading' };
    render(
      <MemoryRouter>
        <AsyncBoundary state={state}>{() => <div>DATA</div>}</AsyncBoundary>
      </MemoryRouter>,
    );
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('renders error view with retry when state is error', () => {
    const state: AsyncState<unknown> = {
      status: 'error',
      error: { code: 'NOT_FOUND', title: '找不到', status: 404 },
    };
    render(
      <MemoryRouter>
        <AsyncBoundary state={state} onRetry={() => undefined}>
          {() => <div>DATA</div>}
        </AsyncBoundary>
      </MemoryRouter>,
    );
    expect(screen.getByText('NOT_FOUND')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });

  it('renders children when state is success and not empty', () => {
    const state: AsyncState<{ name: string }> = { status: 'success', data: { name: 'AAPL' } };
    render(
      <MemoryRouter>
        <AsyncBoundary state={state}>{() => <div>SHOWN</div>}</AsyncBoundary>
      </MemoryRouter>,
    );
    expect(screen.getByText('SHOWN')).toBeInTheDocument();
  });

  it('renders empty view when isEmpty returns true', () => {
    const state: AsyncState<unknown[]> = { status: 'success', data: [] };
    render(
      <MemoryRouter>
        <AsyncBoundary state={state} isEmpty={(d) => d.length === 0}>
          {() => <div>SHOWN</div>}
        </AsyncBoundary>
      </MemoryRouter>,
    );
    expect(screen.getByText('暂无数据')).toBeInTheDocument();
  });
});

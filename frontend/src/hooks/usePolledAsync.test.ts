import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { runAwarePollMs, usePolledAsync } from './usePolledAsync';

describe('usePolledAsync', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('refreshes on the interval without ever dropping back to loading', async () => {
    // The whole reason this hook exists: a timer on the old useAsync would set
    // status to 'loading' every tick and flash the skeleton over live data.
    let n = 0;
    const loader = vi.fn(async () => ++n);
    const seenStatuses: string[] = [];

    const { result } = renderHook(() => {
      const polled = usePolledAsync(loader, [], { pollMs: 1000 });
      seenStatuses.push(polled.state.status);
      return polled;
    });

    await waitFor(() => expect(result.current.state).toEqual({ status: 'success', data: 1 }));
    const statusesAfterFirstLoad = [...seenStatuses];

    await act(async () => {
      vi.advanceTimersByTime(1000);
    });
    await waitFor(() => expect(result.current.state).toEqual({ status: 'success', data: 2 }));

    const statusesDuringRefresh = seenStatuses.slice(statusesAfterFirstLoad.length);
    expect(statusesDuringRefresh).not.toContain('loading');
  });

  it('keeps the last good data when a background refresh fails', async () => {
    // A blip must not replace a screenful of numbers with an error page; it
    // should only mark the data as stale so the UI can say so.
    let attempt = 0;
    const loader = vi.fn(async () => {
      attempt += 1;
      if (attempt === 1) return 'first';
      throw new Error('network down');
    });

    const { result } = renderHook(() => usePolledAsync(loader, [], { pollMs: 1000 }));

    await waitFor(() => expect(result.current.state).toEqual({ status: 'success', data: 'first' }));

    await act(async () => {
      vi.advanceTimersByTime(1000);
    });

    await waitFor(() => expect(result.current.lastError).not.toBeNull());
    expect(result.current.state).toEqual({ status: 'success', data: 'first' });
  });

  it('does not poll while the tab is hidden', async () => {
    // Waiting out a half-hour pipeline with the tab in the background is the
    // normal case; polling there is pure load on a backend that reads Airflow's
    // database on every call.
    const loader = vi.fn(async () => 'x');
    const visibility = vi.spyOn(document, 'visibilityState', 'get');
    visibility.mockReturnValue('visible');

    renderHook(() => usePolledAsync(loader, [], { pollMs: 1000 }));
    await waitFor(() => expect(loader).toHaveBeenCalledTimes(1));

    visibility.mockReturnValue('hidden');
    await act(async () => {
      vi.advanceTimersByTime(3000);
    });
    expect(loader).toHaveBeenCalledTimes(1);

    visibility.mockReturnValue('visible');
    await act(async () => {
      vi.advanceTimersByTime(1000);
    });
    await waitFor(() => expect(loader).toHaveBeenCalledTimes(2));

    visibility.mockRestore();
  });

  it('stops polling entirely when pollMs is null', async () => {
    const loader = vi.fn(async () => 'x');

    renderHook(() => usePolledAsync(loader, [], { pollMs: null }));
    await waitFor(() => expect(loader).toHaveBeenCalledTimes(1));

    await act(async () => {
      vi.advanceTimersByTime(60_000);
    });
    expect(loader).toHaveBeenCalledTimes(1);
  });
});

describe('runAwarePollMs', () => {
  it('slows down but never stops when idle, so a new run is still noticed', () => {
    expect(runAwarePollMs(true)).toBe(5000);
    expect(runAwarePollMs(false)).toBe(30000);
  });
});

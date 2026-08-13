/**
 * 带后台轮询的异步取数 hook。
 *
 * 为什么不是「定时改一个 refreshKey，让原来的 useAsync 重跑」：那条路每次都会先把
 * 状态置回 ``loading``，页面每隔几秒闪一次骨架屏，比不刷新还难用。所以这里把
 * **首次加载**和**后台刷新**分成两条路径：
 *
 * - 首次加载 / 依赖变化 → 走 ``loading``，允许出错误态（此时本来也没数据可显示）
 * - 轮询 / 手动刷新     → 静默：不动 status，成功才替换数据；失败保留旧数据，
 *   只把 ``lastError`` 记下来。网络抖一下不该把一屏好数据换成错误页。
 *
 * 轮询间隔由调用方按数据内容决定（例如「有 run 在跑就 5 秒，否则 30 秒」），
 * 传 ``null`` 完全关闭。标签页不可见时不发请求——用户挂着等半小时是常态，
 * 没必要在后台空转打后端；切回来立刻补一次，保证看到的是当下的状态。
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import { HttpError } from '@/api/http';
import i18n from '@/i18n';
import type { ApiError, AsyncState } from '@/types/api';

const toApiError = (error: unknown): ApiError => {
  if (error instanceof HttpError) return error.apiError;
  return {
    code: 'NETWORK_ERROR',
    title: i18n.t('common.networkError.title'),
    detail: i18n.t('common.networkError.detail'),
    status: 0,
  };
};

const isAbort = (error: unknown): boolean =>
  error instanceof DOMException && error.name === 'AbortError';

export interface PolledAsync<T> {
  state: AsyncState<T>;
  /** 最近一次成功取数的时间戳；null 表示还没成功过。 */
  lastUpdatedAt: number | null;
  /** 后台刷新是否正在进行中（首次加载不算）。 */
  isRefreshing: boolean;
  /** 最近一次后台刷新的失败原因；成功后清空。用于「在刷新，但刷不动」的提示。 */
  lastError: ApiError | null;
  /** 手动触发一次静默刷新。 */
  refresh: () => void;
}

export function usePolledAsync<T>(
  loader: (signal: AbortSignal) => Promise<T>,
  deps: unknown[],
  options: { pollMs?: number | null } = {},
): PolledAsync<T> {
  const { pollMs = null } = options;

  const [state, setState] = useState<AsyncState<T>>({ status: 'idle' });
  const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastError, setLastError] = useState<ApiError | null>(null);

  // loader 每次渲染都是新函数，放进依赖会让 effect 每帧重跑。调用方通过 deps 表达
  // 「什么时候该重新取数」，这里只要始终调到最新的那个闭包。
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  // 静默刷新：不碰 status，失败不覆盖已有数据。
  const refreshRef = useRef<() => void>(() => {});
  const refresh = useCallback(() => {
    const controller = new AbortController();
    setIsRefreshing(true);
    loaderRef.current(controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return;
        setState({ status: 'success', data });
        setLastUpdatedAt(Date.now());
        setLastError(null);
      })
      .catch((error) => {
        if (controller.signal.aborted || isAbort(error)) return;
        setLastError(toApiError(error));
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsRefreshing(false);
      });
  }, []);
  refreshRef.current = refresh;

  // 首次加载 / 依赖变化：走 loading，可以进错误态。
  useEffect(() => {
    const controller = new AbortController();
    setState({ status: 'loading' });
    setLastError(null);
    loaderRef.current(controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return;
        setState({ status: 'success', data });
        setLastUpdatedAt(Date.now());
      })
      .catch((error) => {
        if (controller.signal.aborted || isAbort(error)) return;
        setState({ status: 'error', error: toApiError(error) });
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  // 轮询 + 标签页可见性。
  useEffect(() => {
    if (pollMs === null || pollMs <= 0) return;

    const tick = () => {
      if (document.visibilityState === 'visible') refreshRef.current();
    };
    const timer = window.setInterval(tick, pollMs);

    // 切回前台立刻补一次：轮询在后台是停的，此刻屏幕上的数据可能已经很旧。
    const onVisibility = () => {
      if (document.visibilityState === 'visible') refreshRef.current();
    };
    document.addEventListener('visibilitychange', onVisibility);

    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [pollMs]);

  return { state, lastUpdatedAt, isRefreshing, lastError, refresh };
}

/** 有任务在跑就快轮询，空闲时放慢——空闲时仍要轮询，否则新 run 起来没人发现。 */
export const runAwarePollMs = (hasActive: boolean): number => (hasActive ? 5000 : 30000);

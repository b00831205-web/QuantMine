import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { fetchMe } from '@/api/client/auth';

/**
 * 路由守卫：进入受保护布局前先探测 /auth/me。
 * - loading：不渲染（避免闪现）
 * - 已登录：渲染子树
 * - 未登录：重定向到 /login
 */
type GuardState = 'loading' | 'authed' | 'anon';

export const AuthGuard = ({ children }: { children: ReactNode }) => {
  const [state, setState] = useState<GuardState>('loading');

  useEffect(() => {
    const controller = new AbortController();
    fetchMe(controller.signal)
      .then((user) => {
        if (controller.signal.aborted) return;
        setState(user ? 'authed' : 'anon');
      })
      .catch(() => {
        if (!controller.signal.aborted) setState('anon');
      });
    return () => controller.abort();
  }, []);

  if (state === 'loading') return null;
  if (state === 'anon') return <Navigate to="/login" replace />;
  return <>{children}</>;
};

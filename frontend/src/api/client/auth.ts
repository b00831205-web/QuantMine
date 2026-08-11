import { http } from '@/api/http';
import type { AuthUser } from '@/types/auth';

/** POST /api/v1/auth/login —— 成功后后端下发 HttpOnly 会话 Cookie。 */
export function login(username: string, password: string): Promise<AuthUser> {
  return http<AuthUser>('/api/v1/auth/login', {
    method: 'POST',
    body: { username, password },
  });
}

/** POST /api/v1/auth/logout —— 清除会话 Cookie。 */
export async function logout(): Promise<void> {
  await http('/api/v1/auth/logout', { method: 'POST' });
}

/**
 * GET /api/v1/auth/me —— 登录态探针。
 * 直接用 fetch 而非 http()：401 表示“未登录”，属正常分支，不应抛错。
 */
export async function fetchMe(signal?: AbortSignal): Promise<AuthUser | null> {
  const res = await fetch('/api/v1/auth/me', { credentials: 'include', signal: signal ?? null });
  if (!res.ok) return null;
  return (await res.json()) as AuthUser;
}

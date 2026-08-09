import type { ApiError } from '@/types/api';

/**
 * 统一 HTTP 客户端：fetch + 超时 + AbortController + 错误归一化。
 *
 * 阶段 0 留空具体实现：
 *  - 你需要完成 fetch 封装、超时、状态码到 ApiError 的映射；
 *  - 该函数会被 MSW handler 拦截，不会真正打到后端。
 */

export interface HttpRequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  query?: Record<string, string | number | boolean | undefined | null | Array<string | number>>;
  body?: unknown;
  signal?: AbortSignal | undefined;
  timeoutMs?: number;
}

export class HttpError extends Error {
  constructor(public readonly apiError: ApiError) {
    super(apiError.title);
    this.name = 'HttpError';
  }
}


export async function http<T>(path: string, options: HttpRequestOptions = {}): Promise<T> {
  const { query } = options;
  const url = new URL(path, window.location.origin);
  if (query){
    for (const [key, rawValue] of Object.entries(query)){
      if (rawValue === undefined || rawValue === null){
        continue;
      }
      if (Array.isArray(rawValue)){
        for (const value of rawValue){
          url.searchParams.append(key, String(value))
        }
      } else{
          url.searchParams.append(key, String(rawValue))
      }
    }
  }
  const init: RequestInit = {
    method: options.method ?? 'GET',
    signal: options.signal ?? null,
    // 携带 HttpOnly 会话 Cookie（登录鉴权）；同源代理下默认也会带，显式声明更稳妥
    credentials: 'include',
    ...(options.body !== undefined
      ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(options.body) }
      : {}),
  };
  const response = await fetch(url, init);
  if (!response.ok){
    const apiError = (await response.json()) as ApiError;
    throw new HttpError(apiError)
  }
  return (await response.json()) as T 
}


/**
 * 状态码 → 用户可读中文消息映射。
 *
 * TODO(USER_LEARNING):
 *   目标：把 ApiError 转为页面顶部可展示的中文短句；
 *   覆盖：401 / 403 / 404 / 422 / 429 / 500 / 502 / 503 / 超时 / 默认；
 *   提示：① 区分 title 优先 vs detail 优先；② 包含 traceId 方便反馈。
 */
export function toUserMessage(err: ApiError): string {
  // TODO(USER_LEARNING): 见上方契约
  return err.title ?? '请求失败';
}

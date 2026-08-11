import type { ApiError } from '@/types/api';
import i18n from '@/i18n';

/**
 * Shared HTTP client: fetch, query-string building, AbortController support and
 * error normalization. Non-2xx responses are parsed as an ApiError and rethrown
 * as HttpError, so callers only ever handle one error shape.
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
  if (query) {
    for (const [key, rawValue] of Object.entries(query)) {
      if (rawValue === undefined || rawValue === null) {
        continue;
      }
      if (Array.isArray(rawValue)) {
        for (const value of rawValue) {
          url.searchParams.append(key, String(value));
        }
      } else {
        url.searchParams.append(key, String(rawValue));
      }
    }
  }
  const init: RequestInit = {
    method: options.method ?? 'GET',
    signal: options.signal ?? null,
    // Send the HttpOnly session cookie. A same-origin proxy would include it by
    // default, but stating it explicitly keeps the behavior stable.
    credentials: 'include',
    ...(options.body !== undefined
      ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(options.body) }
      : {}),
  };
  const response = await fetch(url, init);
  if (!response.ok) {
    const apiError = (await response.json()) as ApiError;
    throw new HttpError(apiError);
  }
  return (await response.json()) as T;
}

/**
 * Turn an ApiError into a short, user-readable sentence for the page banner.
 *
 * The backend already localizes `title` per request, so it is used as-is when
 * present; the i18n fallback covers transport failures that never reached the
 * API and therefore carry no server-authored title.
 */
export function toUserMessage(err: ApiError): string {
  return err.title ?? i18n.t('common.requestFailed');
}

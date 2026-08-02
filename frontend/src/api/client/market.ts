import { http } from '@/api/http';
import type { SeriesQuery, SeriesResponse } from '@/types/market';
import type { MarketLatestDateResponse } from '@/types/market';

/**
 * GET /api/v1/market/series
 *
 * TODO(USER_LEARNING):
 *   目标：调用后端时间序列接口，返回多 ticker 归一化结果；
 *   输入：SeriesQuery（含 symbols / startDate / endDate / frequency / normalize）；
 *   输出：SeriesResponse；
 *   约束：① symbols 数组需要拼成 query（重复 key 或逗号分隔，按后端约定）；
 *         ② frequency 缺省 'D'；③ 失败时让上层 AsyncBoundary 捕获；
 *   提示：使用上面已留空的 http()，配合 types/market 中的类型即可。
 */
export function fetchSeries(
  query: SeriesQuery,
  signal?: AbortSignal,
): Promise<SeriesResponse> {
  return http<SeriesResponse>(
    '/api/v1/market/series',
    {
      query: {
        symbols: query.symbols,
        startDate: query.startDate,
        endDate: query.endDate,
        frequency: query.frequency,
        normalize: query.normalize,
      },
      signal,
    },
  );
}

export function fetchLatestMarketDate(): Promise<MarketLatestDateResponse>{
  return http<MarketLatestDateResponse>('/api/v1/market/latest-date')
}
import { http } from '@/api/http';
import type { SeriesPoint } from '@/types/market';
import type {
  RebalanceDetail,
  RebalancePage,
  RebalanceQuery,
} from '@/types/rebalance';

/** GET /api/v1/rebalances —— 调仓列表（分页） */
export function fetchRebalances(
  query: RebalanceQuery,
  signal?: AbortSignal,
): Promise<RebalancePage> {
  return http<RebalancePage>('/api/v1/rebalances',
  {
    query:{
        backtestJob: query.backtestJob,
        variant: query.variant,
        factor: query.factor,
        tradeDate: query.tradeDate,
        page: query.page,
        pageSize: query.pageSize
    },
    signal,
}
  );
}
/** GET /api/v1/rebalances/{rebalanceId} —— 详情（含 holdings + contributions） */
export function fetchRebalanceDetail(
  rebalanceId: string,
  signal?: AbortSignal,
): Promise<RebalanceDetail> {
    return http<RebalanceDetail>(
        `/api/v1/rebalances/${rebalanceId}`,
       {signal}, 
    );
  // TODO(USER_LEARNING): 请求 /api/v1/rebalances/${rebalanceId}，注意路径参数怎么拼
}

export function fetchRebalanceReturns(
  rebalanceId: string,
  signal?: AbortSignal,
): Promise<{ series: SeriesPoint[] }> {
    return http<{series: SeriesPoint[]}>(
        `/api/v1/rebalances/${rebalanceId}/returns`,
        {signal},
    );
}

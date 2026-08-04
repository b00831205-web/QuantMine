import { http } from '@/api/http';
import type {
  Catalog,
  DataPage,
  DataQuery,
  QueryResult,
  StructuredQueryPayload,
} from '@/types/data';

/** GET /api/v1/data/catalog —— 白名单资源与字段说明 */
export function fetchDataCatalog(signal?: AbortSignal): Promise<Catalog[]> {
  return http<Catalog[]>('/api/v1/data/catalog', { signal });
}

/** GET /api/v1/data/{resource} —— 资源数据（筛选/排序/分页） */
export function fetchDataPage(query: DataQuery, signal?: AbortSignal): Promise<DataPage> {
  return http<DataPage>(`/api/v1/data/${query.resource}`, {
    query: {
      ...(query.filters ? { filters: JSON.stringify(query.filters) } : {}),
      ...(query.sortBy ? { sortBy: query.sortBy } : {}),
      ...(query.sortDir ? { sortDir: query.sortDir } : {}),
      ...(query.page !== undefined ? { page: query.page } : {}),
      ...(query.pageSize !== undefined ? { pageSize: query.pageSize } : {}),
    },
    signal,
  });
}

/** GET /api/v1/data/{resource}/export —— CSV 下载链接 */
export function buildDataExportUrl(query: DataQuery): string {
  const params = new URLSearchParams();
  if (query.filters) {
    params.set('filters', JSON.stringify(query.filters));
  }
  return `/api/v1/data/${query.resource}/export?${params}`;
}

/** POST /api/v1/data/query/structured —— 结构化查询 */
export function fetchStructuredQuery(
  payload: StructuredQueryPayload,
  signal?: AbortSignal,
): Promise<QueryResult> {
  return http<QueryResult>('/api/v1/data/query/structured', {
    method: 'POST',
    body: payload,
    signal,
  });
}

/** POST /api/v1/data/query/sql —— 受限 SQL 查询（仅 SELECT） */
export function fetchSqlQuery(sql: string, signal?: AbortSignal): Promise<QueryResult> {
  return http<QueryResult>('/api/v1/data/query/sql', {
    method: 'POST',
    body: { sql },
    signal,
  });
}

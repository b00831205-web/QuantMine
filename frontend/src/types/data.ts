import type { Page } from './api';

/** 白名单资源名 */
export type DataResource =
  | 'market_latest'
  | 'market_bars'
  | 'research_runs'
  | 'test_results'
  | 'backtest_results'
  | 'backtest_metrics';

export interface CatalogField {
  name: string;
  type: 'string' | 'number' | 'date' | 'boolean';
  description: string;
  filterable: boolean;
}

export interface Catalog {
  resource: DataResource;
  label: string;
  description: string;
  fields: CatalogField[];
}

export interface DataQuery {
  resource: DataResource;
  filters?: Record<string, string | number | boolean | Array<string | number>>;
  sortBy?: string;
  sortDir?: 'asc' | 'desc';
  page?: number;
  pageSize?: number;
}

export type DataPage = Page<Record<string, unknown>>;

/** 结构化查询：条件（字段 + 操作符 + 值） */
export interface StructuredCondition {
  field: string;
  op: 'eq' | 'ne' | 'gt' | 'lt' | 'contains';
  value: string | number;
}

export interface StructuredQueryPayload {
  resource: DataResource;
  fields: string[];
  conditions: StructuredCondition[];
  limit?: number;
}

/** 查询结果：列名 + 行数据 */
export interface QueryResult {
  columns: string[];
  rows: Array<Record<string, unknown>>;
}

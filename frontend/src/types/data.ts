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

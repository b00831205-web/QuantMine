/**
 * 公共 API 类型：覆盖 §8 统一错误响应、四态异步状态、分页。
 * 阶段 0 仅声明契约，不连接真实后端。
 */

/** 与 docs/api/openapi.yaml 中 ErrorResponse schema 一一对应 */
export interface ApiError {
  /** 业务错误码，如 UNAUTHENTICATED / VALIDATION_FAILED / NOT_FOUND / UPSTREAM_FAILURE */
  code: string;
  /** 面向用户的中文短标题 */
  title: string;
  /** 详细说明，可选 */
  detail?: string;
  /** 后端原始 trace_id，便于排查 */
  traceId?: string;
  /** 字段级错误（VALIDATION_FAILED 时返回） */
  fieldErrors?: Array<{ field: string; message: string }>;
  /** HTTP 状态码 */
  status: number;
}

/** 异步状态机：idle → loading → success | error */
export type AsyncState<T> =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success'; data: T }
  | { status: 'error'; error: ApiError };

/** 通用分页响应 */
export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
}

/** 通用时间区间 */
export interface DateRange {
  startDate: string; // ISO date YYYY-MM-DD
  endDate: string;
}

/** 频率：日 / 周 / 月，长区间降采样用 */
export type Frequency = 'D' | 'W' | 'M';

/** 货币 / 收益率单位 */
export type Unit = 'percent' | 'decimal';

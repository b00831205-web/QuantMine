/**
 * Single source of truth mapping Airflow state to color and label.
 *
 * The list page's "recent runs" swatches, the last-run status dot, and later the
 * graph view's node coloring all reuse this, which keeps the palette consistent
 * across the app. Colors are always design tokens (CSS variables) so they follow
 * the active theme.
 */

import i18n from '@/i18n';

/** Raw values of dag_run.state / task_instance.state (null means no state yet). */
export type AirflowState =
  | 'success'
  | 'failed'
  | 'running'
  | 'queued'
  | 'scheduled'
  | 'skipped'
  | 'upstream_failed'
  | 'up_for_retry'
  | 'up_for_reschedule'
  | 'deferred'
  | 'removed'
  | 'restarting'
  | 'none'
  | null;

/** 状态 → CSS 变量颜色。未知状态回退到中性色。 */
export const STATE_COLOR: Record<string, string> = {
  success: 'var(--positive)',
  failed: 'var(--negative)',
  running: 'var(--info)',
  queued: 'var(--warning)',
  scheduled: 'var(--accent)',
  skipped: 'var(--text-muted)',
  upstream_failed: 'var(--warning)',
  up_for_retry: 'var(--warning)',
  up_for_reschedule: 'var(--warning)',
  deferred: 'var(--info)',
  removed: 'var(--text-muted)',
  restarting: 'var(--warning)',
  none: 'var(--border-subtle)',
};

/** 状态 → 中文短标签。 */
export const STATE_LABEL: Record<string, string> = {
  success: '成功',
  failed: '失败',
  running: '运行中',
  queued: '排队中',
  scheduled: '已调度',
  skipped: '跳过',
  upstream_failed: '上游失败',
  up_for_retry: '待重试',
  up_for_reschedule: '待重排',
  deferred: '延迟',
  removed: '已移除',
  restarting: '重启中',
  none: '无状态',
};

const NEUTRAL = 'var(--border-subtle)';

export function stateColor(state: AirflowState | string | undefined): string {
  if (!state) return NEUTRAL;
  return STATE_COLOR[state] ?? 'var(--text-muted)';
}

export function stateLabel(state: AirflowState | string | undefined): string {
  if (!state) return i18n.t('workflow.state.none', { defaultValue: '无状态' });
  return i18n.t(`workflow.state.${state}`, { defaultValue: STATE_LABEL[state] ?? state });
}

/** 列表页/图例展示的核心状态（对应需求：通过 / 失败 / 进行中 / 跳过）。 */
export const CORE_LEGEND: Array<{ state: string; label: string }> = [
  { state: 'success', label: '成功' },
  { state: 'failed', label: '失败' },
  { state: 'running', label: '运行中' },
  { state: 'skipped', label: '跳过' },
  { state: 'queued', label: '排队中' },
  { state: 'upstream_failed', label: '上游失败' },
];

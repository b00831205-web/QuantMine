import type { TaskInstanceInfo } from '@/types/workflow';
import { stateColor, stateLabel } from '@/utils/workflowStatus';
import { fmtDuration } from '@/utils/format';

/**
 * 任务耗时柱状图（纯 inline 样式）。每个任务一根竖柱，高度 ∝ 时长，按状态着色。
 * 运行中/未结束任务用兜底时长的斜纹柱表示"进行中"；无实例任务留空列。
 */
export const TaskBarChart = ({
  tasks,
  height = 180,
}: {
  tasks: TaskInstanceInfo[];
  height?: number;
}) => {
  const durations = tasks
    .map((t) => t.durationMs)
    .filter((v): v is number => v !== null && v > 0);
  const fallbackDur =
    durations.length > 0
      ? durations.slice().sort((a, b) => a - b)[Math.floor(durations.length / 2)]!
      : 60000;
  const maxDur = Math.max(fallbackDur, ...durations);

  const barDur = (t: TaskInstanceInfo): number => {
    if (t.durationMs && t.durationMs > 0) return t.durationMs;
    if (t.state === 'running') return fallbackDur;
    return 0;
  };

  if (tasks.length === 0) {
    return (
      <div style={{ color: 'var(--text-muted)', fontSize: 'var(--fs-sm)', padding: 'var(--sp-3)' }}>
        该运行暂无任务数据
      </div>
    );
  }

  return (
    <div>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 2 }}>
        最长 {fmtDuration(maxDur)}
      </div>
      {/* 绘图区 */}
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-end',
          gap: 8,
          height,
          borderBottom: '1px solid var(--border-subtle)',
          borderLeft: '1px solid var(--border-subtle)',
          paddingLeft: 4,
        }}
      >
        {tasks.map((t) => {
          const dur = barDur(t);
          const pct = maxDur > 0 ? (dur / maxDur) * 100 : 0;
          const running = t.state === 'running';
          return (
            <div
              key={t.taskId}
              title={`${t.taskId} · ${stateLabel(t.state)}${dur > 0 ? ` · ${fmtDuration(dur)}` : ''}`}
              style={{
                flex: 1,
                height: '100%',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'flex-end',
                alignItems: 'center',
              }}
            >
              <div
                style={{
                  width: '62%',
                  height: `${pct}%`,
                  minHeight: dur > 0 ? 4 : 0,
                  background: stateColor(t.state),
                  borderRadius: '4px 4px 0 0',
                  opacity: running ? 0.7 : 1,
                  backgroundImage: running
                    ? 'repeating-linear-gradient(45deg, rgba(255,255,255,0.35) 0 6px, transparent 6px 12px)'
                    : undefined,
                }}
              />
            </div>
          );
        })}
      </div>
      {/* x 轴标签 */}
      <div style={{ display: 'flex', gap: 8, marginTop: 4, paddingLeft: 4 }}>
        {tasks.map((t) => (
          <div
            key={t.taskId}
            title={t.taskId}
            style={{
              flex: 1,
              minWidth: 0,
              fontSize: 10,
              color: 'var(--text-muted)',
              textAlign: 'center',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}
          >
            {t.taskId}
          </div>
        ))}
      </div>
    </div>
  );
};

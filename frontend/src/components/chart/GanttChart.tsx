import { useEffect, useRef } from 'react';
import * as echarts from 'echarts/core';
import { BarChart } from 'echarts/charts';
import { GridComponent, TooltipComponent, DataZoomComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import type { TaskInstance } from '@/types/workflow';
import { useTranslation } from 'react-i18next';

echarts.use([BarChart, GridComponent, TooltipComponent, DataZoomComponent, CanvasRenderer]);

const STATUS_COLOR: Record<TaskInstance['status'], string> = {
  success: 'var(--positive)',
  failed: 'var(--negative)',
  running: 'var(--info)',
  skipped: 'var(--text-muted)',
  upstream_failed: 'var(--warning)',
};

/** '2026-08-03 00:00:02' → 从 0 点起的分钟数（只解析时间部分，避免时区问题） */
const parseMinute = (value: string): number => {
  const time = value.split(' ')[1] ?? '00:00:00';
  const [h = 0, m = 0, s = 0] = time.split(':').map(Number);
  return h * 60 + m + s / 60;
};

export const GanttChart = ({
  tasks,
  visibleCount,
}: {
  tasks: TaskInstance[];
  /** 只显示前 N 个任务（模拟运行推进，横轴随任务增加） */
  visibleCount?: number;
}) => {
  const { t } = useTranslation();
  const ref = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    chartRef.current = echarts.init(ref.current, undefined, { renderer: 'canvas' });
    const observer = new ResizeObserver(() => chartRef.current?.resize());
    observer.observe(ref.current);
    return () => {
      observer.disconnect();
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!chartRef.current) return;

    const visible = tasks.slice(0, visibleCount ?? tasks.length);
    const rows = visible
      .filter((t) => t.startTime !== null && t.durationMs !== null)
      .map((t) => ({
        taskId: t.taskId,
        status: t.status,
        startMin: parseMinute(t.startTime as string),
        durationMin: (t.durationMs as number) / 60000,
      }))
      .sort((a, b) => a.startMin - b.startMin);

    // 横轴偏移基准：最早任务的开始时间
    const baseMin = rows[0]?.startMin ?? 0;
    const data = rows.map((r) => ({ ...r, startMin: r.startMin - baseMin }));

    // 全量任务的时间上限，作为 Y 轴缩放的 100% 基准
    const allEnds = tasks
      .filter((t) => t.startTime !== null && t.durationMs !== null)
      .map((t) => parseMinute(t.startTime as string) + (t.durationMs as number) / 60000);
    const yMax = Math.max(0, ...allEnds) - baseMin || 1;

    // 聚焦最后一个可见任务：横轴显示最近 1~2 个，纵轴聚焦其耗时区间（±8% 边距）
    const n = data.length;
    const focus = n > 0 ? data[n - 1] : undefined;
    const xStart = n > 1 ? Math.max(0, 100 - (2 / n) * 100) : 0;
    const yStart = focus ? Math.max(0, (focus.startMin / yMax) * 100 - 8) : 0;
    const yEnd = focus
      ? Math.min(100, ((focus.startMin + focus.durationMin) / yMax) * 100 + 8)
      : 100;

    chartRef.current.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: 50, right: 24, top: 16, bottom: 50 },
      xAxis: {
        type: 'category',
        data: data.map((r) => r.taskId),
        axisLabel: { rotate: 30 },
      },
      yAxis: {
        type: 'value',
        name: t('workflow.gantt.minutes'),
      },
      dataZoom: [
        { id: 'x-slider', type: 'slider', xAxisIndex: 0, bottom: 6, height: 10, show: false },
        { type: 'inside', xAxisIndex: 0, start: xStart, end: 100, moveOnMouseMove: true },
        { type: 'inside', yAxisIndex: 0, start: yStart, end: yEnd },
      ],
      series: [
        {
          type: 'bar',
          stack: 'gantt',
          itemStyle: { color: 'transparent' },
          data: data.map((r) => r.startMin),
          barWidth: 24,
        },
        {
          type: 'bar',
          stack: 'gantt',
          barWidth: 24,
          itemStyle: {
            color: (params: { dataIndex: number }) => {
              const row = data[params.dataIndex];
              return STATUS_COLOR[row?.status ?? 'skipped'];
            },
          },
          data: data.map((r) => r.durationMin),
        },
      ],
    });
  }, [tasks, visibleCount, t]);

  return (
    <div
      ref={ref}
      onMouseEnter={() =>
        chartRef.current?.setOption({ dataZoom: [{ id: 'x-slider', show: true }] })
      }
      onMouseLeave={() =>
        chartRef.current?.setOption({ dataZoom: [{ id: 'x-slider', show: false }] })
      }
      style={{ width: '100%', height: '100%' }}
    />
  );
};

import { useEffect, useRef } from 'react';
import * as echarts from 'echarts/core';
import { LineChart } from 'echarts/charts';
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  ToolboxComponent,
  MarkLineComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import type { SeriesPoint } from '@/types/market';
import { normalizeToBase100 } from './normalize';

echarts.use([
  LineChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  ToolboxComponent,
  MarkLineComponent,
  CanvasRenderer,
]);

export interface SeriesDescriptor {
  symbol: string;
  points: SeriesPoint[];
}

interface Props {
  series: SeriesDescriptor[];
  // 显式 | undefined：exactOptionalPropertyTypes 下调用方会条件式传入 undefined
  baseDate?: string | undefined;
  height?: number;
  /** 是否对所有曲线归一化到基期 100（默认 true） */
  normalize?: boolean;
  /** 点击“还原”图标后回调（由页面负责重置回初始状态） */
  onReset?: () => void;
  /** 启用“走势绘制”入场动画：曲线从左到右逐点绘制，多序列依次入场 */
  drawEffect?: boolean;
}

export const SeriesChart = ({
  series,
  height = 360,
  normalize = true,
  onReset,
  drawEffect = false,
}: Props) => {
  const ref = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const onResetRef = useRef(onReset);
  const lastOptionRef = useRef<Record<string, unknown> | null>(null);
  onResetRef.current = onReset;

  useEffect(() => {
    if (!ref.current) return;
    chartRef.current = echarts.init(ref.current, undefined, { renderer: 'canvas' });
    // 内置 restore 图标点击后，除了重置图表本身，还要通知页面恢复初始股票/区间
    chartRef.current.on('restore', () => onResetRef.current?.());
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
    const datasets = series.map((s) => ({
      name: s.symbol,
      data: (normalize ? normalizeToBase100(s.points) : s.points).map((p) => [p.date, p.value]),
    }));
    const seriesOption = datasets.map((d) => ({
      name: d.name,
      type: 'line',
      showSymbol: false,
      data: d.data,
    }));
    const drawOption = drawEffect
      ? {
          animation: true,
          animationDuration: 1200,
          animationEasing: 'cubicOut' as const,
          series: seriesOption.map((s, i) => ({
            ...s,
            animationDelay: (idx: number) => idx * 2 + i * 250,
          })),
        }
      : {};
    const option = {
      tooltip: { trigger: 'axis' },
      legend: { top: 0, textStyle: { color: '#9aa3b8' } },
      grid: { left: 50, right: 20, top: 36, bottom: 50 },
      xAxis: { type: 'time' },
      yAxis: { type: 'value', scale: true },
      dataZoom: [
        { type: 'inside', xAxisIndex: 0 },
        { type: 'slider', xAxisIndex: 0, height: 18, bottom: 12 },
      ],
      toolbox: {
        right: 8,
        feature: { dataZoom: { yAxisIndex: 'none' }, restore: {} },
      },
      series: seriesOption,
      ...drawOption,
    };
    lastOptionRef.current = option;
    if (drawEffect) {
      // 保证每次数据写入都重放完整“走势绘制”动画：
      // 实例已存在（HMR 更新 / 数据变化）时也生效，而不是只在新挂载时播放。
      chartRef.current.clear();
      chartRef.current.setOption(option, { notMerge: true });
      return;
    }
    chartRef.current.setOption(option);
  }, [series, normalize, drawEffect]);

  // 页面在后台加载时会吞掉动画（RAF 不跑）；回到前台时重放走势动画。
  useEffect(() => {
    const replayOnVisible = () => {
      if (!drawEffect || document.visibilityState !== 'visible') return;
      const option = lastOptionRef.current;
      if (!option || !chartRef.current) return;
      chartRef.current.clear();
      chartRef.current.setOption(option, { notMerge: true });
    };
    document.addEventListener('visibilitychange', replayOnVisible);
    return () => document.removeEventListener('visibilitychange', replayOnVisible);
  }, [drawEffect]);

  return <div ref={ref} style={{ width: '100%', height }} />;
};

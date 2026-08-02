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
}

export const SeriesChart = ({ series, height = 360, normalize = true }: Props) => {
  const ref = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    chartRef.current = echarts.init(ref.current, undefined, { renderer: 'canvas' });
    const onResize = () => chartRef.current?.resize();
    window.addEventListener('resize', onResize);
    return () => {
      window.removeEventListener('resize', onResize);
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
    chartRef.current.setOption({
      tooltip: { trigger: 'axis' },
      legend: { top: 0, textStyle: { color: '#9aa3b8' } },
      grid: { left: 50, right: 20, top: 36, bottom: 50 },
      xAxis: { type: 'time' },
      yAxis: { type: 'value', scale: true },
      dataZoom: [
        { type: 'inside' },
        { type: 'slider', height: 18, bottom: 12 },
      ],
      toolbox: { right: 8, feature: { dataZoom: {}, restore: {} } },
      series: datasets.map((d) => ({
        name: d.name,
        type: 'line',
        showSymbol: false,
        data: d.data,
      })),
    });
  }, [series, normalize]);

  return <div ref={ref} style={{ width: '100%', height }} />;
};

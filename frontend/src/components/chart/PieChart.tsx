import { useEffect, useRef } from 'react';
import * as echarts from 'echarts/core';
import { PieChart as EchartsPie } from 'echarts/charts';
import { TooltipComponent, LegendComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([EchartsPie, TooltipComponent, LegendComponent, CanvasRenderer]);

export interface PieDatum {
  name: string;
  value: number;
}

/** 扇面分段配色的低饱和蓝阶（前 10 扇） */
export const SEGMENTED_PALETTE = [
  '#8ab4ff',
  '#6ea0ff',
  '#4f8cff',
  '#3d7df2',
  '#356ecc',
  '#2f60aa',
  '#2a5492',
  '#25497e',
  '#21406c',
  '#1d385c',
] as const;

/** 扇面分段中「其他」聚合扇的静默中性色 */
export const SEGMENTED_OTHER_COLOR = '#2a3142';

interface Props {
  data: PieDatum[];
  height?: number;
  /** 是否显示图例。持仓很多（几十只）时图例会铺满并盖住饼图，传 false 关闭。 */
  showLegend?: boolean;
  /** 扇面分段效果：扇区间隙、低饱和配色、逐扇展开动画 */
  segmented?: boolean;
  /** 自定义扇区配色；segmented 时默认使用低饱和蓝阶 + 「其他」中性色 */
  colors?: string[];
}

export const PieChart = ({
  data,
  height = 260,
  showLegend = true,
  segmented = false,
  colors,
}: Props) => {
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
    const palette =
      colors ?? (segmented ? [...SEGMENTED_PALETTE, SEGMENTED_OTHER_COLOR] : undefined);
    const segmentedOption = segmented
      ? {
          animationType: 'expansion' as const,
          animationEasing: 'cubicOut' as const,
          animationDelay: (idx: number) => idx * 55,
          itemStyle: {
            borderRadius: 4,
            borderColor: '#161a22',
            borderWidth: 2,
          },
          emphasis: {
            scale: true,
            scaleSize: 6,
          },
        }
      : {};
    chartRef.current.setOption({
      color: palette ?? data.map((_, i) => `hsl(${Math.round((i / data.length) * 360)}, 65%, 55%)`),
      tooltip: { trigger: 'item' },
      legend: showLegend
        ? { type: 'scroll', bottom: 0, textStyle: { color: '#9aa3b8' } }
        : { show: false },
      series: [
        {
          type: 'pie',
          radius: ['45%', '70%'],
          label: false,
          data,
          ...segmentedOption,
        },
      ],
    });
  }, [data, showLegend, segmented, colors]);

  return <div ref={ref} style={{ width: '100%', height }} />;
};

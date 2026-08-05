import {useEffect, useRef} from 'react'
import * as echarts from 'echarts/core'
import { PieChart as EchartsPie} from 'echarts/charts';
import { TooltipComponent, LegendComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([EchartsPie, TooltipComponent, LegendComponent, CanvasRenderer])

export interface PieDatum{
    name: string;
    value: number;
}

interface Props{
    data: PieDatum[];
    height?: number;
    /** 是否显示图例。持仓很多（几十只）时图例会铺满并盖住饼图，传 false 关闭。 */
    showLegend?: boolean;
}

export const PieChart = ({data, height = 260, showLegend = true}: Props) =>{
    const ref = useRef<HTMLDivElement| null>(null);
    const chartRef = useRef<echarts.ECharts|null>(null); 

    useEffect(()=>{
        if (!ref.current) return;
        chartRef.current = echarts.init(ref.current, undefined, {renderer: 'canvas'});
        const observer = new ResizeObserver(()=>chartRef.current?.resize());
        observer.observe(ref.current);
        return ()=> {
            observer.disconnect();
            chartRef.current?.dispose();
            chartRef.current = null;
        };
    },[]
)
    useEffect(()=>{
        if (!chartRef.current) return;
        chartRef.current.setOption({
            color : data.map((_, i)=> `hsl(${Math.round((i/data.length) * 360)}, 65%, 55%)`),
            tooltip:{trigger: 'item'},
            legend: showLegend
                ? {type: 'scroll', bottom: 0, textStyle: {color: '#9aa3b8'}}
                : {show: false},
            series: [{
                type: 'pie',
                radius: ['45%','70%'],
                label: false,
                data,
            },
        ],
        });
    },[data, showLegend]);
    return <div ref={ref} style = {{width: '100%', height}}/>
};

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
}

export const PieChart = ({data, height = 260}: Props) =>{
    const ref = useRef<HTMLDivElement| null>(null);
    const chartRef = useRef<echarts.ECharts|null>(null); 

    useEffect(()=>{
        if (!ref.current) return;
        chartRef.current = echarts.init(ref.current, undefined, {renderer: 'canvas'});
        const onResize = ()=>chartRef.current?.resize();
        window.addEventListener('resize', onResize);
        return ()=> {
            window.removeEventListener('resize', onResize)
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
            legend: {bottom: 0, textSyle: {color: '#9aa3b8'}},
            series: [{
                type: 'pie',
                radius: ['45%','70%'],
                label: false,
                data,
            },
        ],
        });
    },[data]);
    return <div ref={ref} style = {{width: '100%', height}}/>
};
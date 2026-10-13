import { BarChart, LineChart } from 'echarts/charts';
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TitleComponent,
  TooltipComponent,
} from 'echarts/components';
import * as echarts from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { useEffect, useRef } from 'react';

// 按需注册：只引图表真正用到的模块，避免把整个 ECharts 打进包里
echarts.use([
  BarChart,
  LineChart,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TitleComponent,
  TooltipComponent,
  CanvasRenderer,
]);

export type EChartOption = echarts.EChartsCoreOption;

interface EChartProps {
  option: EChartOption;
  height?: number;
  ariaLabel?: string;
}

// 极简 ECharts 封装：echarts-for-react 与 React 19 的兼容性没有保障，
// 自己包一层反而更可控，也少一个依赖。
export function EChart({ option, height = 320, ariaLabel }: EChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const chart = echarts.init(container);
    chartRef.current = chart;

    const handleResize = () => chart.resize();
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    // notMerge=true：切换时间范围后序列数量会变，必须整体替换而不是合并
    chartRef.current?.setOption(option, true);
  }, [option]);

  return (
    <div ref={containerRef} role="img" aria-label={ariaLabel} style={{ width: '100%', height }} />
  );
}

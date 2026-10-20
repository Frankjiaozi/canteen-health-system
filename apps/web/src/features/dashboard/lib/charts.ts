import { calendarRows } from './calendar';
import type { ComplianceResponse, TrendsResponse, WasteResponse } from '../types';
import { toNumber } from './format';
const CHART_INK = '#22312a';
const CHART_MUTED = '#647268';
const CHART_LINE = '#e9e4d7';
const CHART_GREEN = '#779373';
const CHART_AMBER = '#bba27a';
const CHART_SAGE = '#cf947a';

const axisLabel = { color: CHART_MUTED, fontSize: 11 };

const tooltipBase = {
  backgroundColor: CHART_INK,
  borderWidth: 0,
  padding: [9, 12],
  textStyle: { color: '#f6f1e4', fontSize: 12 },
  axisPointer: {
    type: 'line' as const,
    lineStyle: { color: '#b8c4b9', type: 'dashed' as const, width: 1 },
  },
};

const legendBase = {
  top: 0,
  right: 0,
  icon: 'circle',
  itemWidth: 8,
  itemHeight: 8,
  itemGap: 18,
  textStyle: { color: '#5f7166', fontSize: 12 },
};

const xAxisBase = {
  type: 'category' as const,
  axisLine: { lineStyle: { color: CHART_LINE } },
  axisTick: { show: false },
  axisLabel,
};

const yAxisBase = {
  type: 'value' as const,
  axisLabel,
  splitLine: { lineStyle: { color: '#f0ece2', type: 'dashed' as const } },
};

const chartTextStyle = {
  fontFamily: '"PingFang SC", "Microsoft YaHei", "Segoe UI", sans-serif',
};

export function buildTrendOption(data?: TrendsResponse) {
  const points = calendarRows(data);
  const dates = points.map((point) => point.date.slice(5));

  return {
    textStyle: chartTextStyle,
    color: [CHART_GREEN, CHART_AMBER, CHART_SAGE],
    tooltip: { ...tooltipBase, trigger: 'axis' },
    // 图例放顶部：默认的底部居中被横轴日期标签压住，读起来很挤
    legend: { ...legendBase, data: ['食用油', '食盐', '添加糖'] },
    grid: { left: 56, right: 22, top: 44, bottom: 45 },
    xAxis: {
      ...xAxisBase,
      data: dates,
      boundaryGap: false,
      axisLabel: {
        ...axisLabel,
        interval: points.length <= 14 ? 0 : 'auto',
        rotate: points.length > 7 ? 35 : 0,
        showMinLabel: true,
        showMaxLabel: true,
      },
    },
    yAxis: { ...yAxisBase, name: '克', nameTextStyle: { color: CHART_MUTED, fontSize: 11 } },
    series: [
      {
        name: '食用油',
        type: 'line',
        smooth: 0.35,
        showSymbol: true,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { width: 2.4 },
        areaStyle: { opacity: 0.08 },
        data: points.map((point) => toNumber(point.point?.oil_total_g)),
      },
      {
        name: '食盐',
        type: 'line',
        smooth: 0.35,
        showSymbol: true,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { width: 2.4 },
        areaStyle: { opacity: 0.06 },
        data: points.map((point) => toNumber(point.point?.salt_total_g)),
      },
      {
        name: '添加糖',
        type: 'line',
        smooth: 0.35,
        showSymbol: true,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { width: 2 },
        data: points.map((point) => toNumber(point.point?.sugar_total_g)),
      },
    ],
  };
}

export function buildComplianceOption(data?: ComplianceResponse) {
  const points = calendarRows(data);

  return {
    textStyle: chartTextStyle,
    tooltip: {
      ...tooltipBase,
      trigger: 'axis',
      valueFormatter: (value: unknown) =>
        typeof value === 'number' ? `${(value * 100).toFixed(1)}%` : String(value),
    },
    grid: { left: 48, right: 18, top: 24, bottom: 30 },
    xAxis: { ...xAxisBase, data: points.map((point) => point.date.slice(5)) },
    yAxis: {
      ...yAxisBase,
      max: 1,
      name: '达标率',
      nameTextStyle: { color: CHART_MUTED, fontSize: 11 },
      // 纵轴按百分比读，0.5 这种刻度对使用者没有意义
      axisLabel: {
        ...axisLabel,
        formatter: (value: number) => `${Math.round(value * 100)}%`,
      },
    },
    series: [
      {
        name: '达标率',
        type: 'bar',
        barWidth: '48%',
        itemStyle: { color: CHART_GREEN, borderRadius: [5, 5, 0, 0] },
        data: points.map((point) => toNumber(point.point?.rate, 4)),
      },
    ],
  };
}

export function buildWasteOption(data?: WasteResponse) {
  const points = calendarRows(data);

  return {
    textStyle: chartTextStyle,
    color: [CHART_AMBER, CHART_GREEN],
    tooltip: { ...tooltipBase, trigger: 'axis' },
    legend: { ...legendBase, data: ['浪费率', '剩餐量'] },
    grid: { left: 56, right: 56, top: 44, bottom: 30 },
    xAxis: { ...xAxisBase, data: points.map((point) => point.date.slice(5)) },
    yAxis: [
      {
        ...yAxisBase,
        name: '浪费率',
        nameTextStyle: { color: CHART_MUTED, fontSize: 11 },
        // 不写死上限：浪费率通常在 10% 上下，固定到 100% 会把柱子压成一条线
        axisLabel: {
          ...axisLabel,
          formatter: (value: number) => `${Math.round(value * 100)}%`,
        },
      },
      {
        type: 'value',
        name: '千克',
        nameTextStyle: { color: CHART_MUTED, fontSize: 11 },
        position: 'right',
        axisLabel,
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: '浪费率',
        type: 'bar',
        barWidth: '48%',
        itemStyle: { color: CHART_AMBER, borderRadius: [5, 5, 0, 0] },
        data: points.map((point) => toNumber(point.point?.waste_ratio, 4)),
      },
      {
        name: '剩餐量',
        type: 'line',
        smooth: 0.35,
        showSymbol: true,
        lineStyle: { width: 2.4, color: CHART_GREEN },
        itemStyle: { color: CHART_GREEN },
        yAxisIndex: 1,
        data: points.map((point) =>
          point.point?.leftover_weight_g == null
            ? null
            : Number(point.point.leftover_weight_g) / 1000,
        ),
      },
    ],
  };
}

import { Card, Col, Row, Segmented, Skeleton, Space, Table, Tabs, Tag, Typography } from 'antd';
import type { TableProps } from 'antd';
import { useState, type ReactNode } from 'react';
import { EChart, type EChartOption } from '@/shared/components/EChart';
import { MenuOverview } from '../components/MenuOverview';
import { useDashboard } from '../hooks/useDashboard';
import { RANGE_OPTIONS, formatPercent, toNumber, trimDecimal } from '../lib/format';
import type {
  ComplianceResponse,
  StandardComparison,
  TrendsResponse,
  WasteResponse,
} from '../types';
import './dashboard.css';

const STATUS_COLOR: Record<string, string> = {
  ok: 'success',
  over: 'error',
  under: 'warning',
  unknown: 'default',
};

const STATUS_TEXT: Record<string, string> = {
  ok: '达标',
  over: '超出上限',
  under: '低于推荐',
  unknown: '暂无数据',
};

const CHART_INK = '#22312a';
const CHART_MUTED = '#647268';
const CHART_LINE = '#e9e4d7';
const CHART_GREEN = '#3f6f57';
const CHART_AMBER = '#b07b32';
const CHART_SAGE = '#6f8274';

const axisLabel = { color: CHART_MUTED, fontSize: 11 };

interface MetricProps {
  label: string;
  value: ReactNode;
  unit?: string;
  hint?: string;
  loading?: boolean;
  lead?: boolean;
}

function Metric({ label, value, unit, hint, loading, lead }: MetricProps) {
  return (
    <div className={`zw-metric${lead ? ' is-lead' : ''}`}>
      <span className="zw-metric-label">{label}</span>
      {loading ? (
        <Skeleton.Button active size="small" className="zw-metric-skeleton" />
      ) : (
        <span className="zw-metric-value">
          {value}
          {unit ? <small>{unit}</small> : null}
        </span>
      )}
      {hint ? <span className="zw-metric-hint">{hint}</span> : null}
    </div>
  );
}

export function DashboardPage() {
  const [days, setDays] = useState<number>(14);
  const { summary, trends, perCapita, compliance, waste } = useDashboard(days);
  const rangeLabel =
    RANGE_OPTIONS.find((option) => option.value === days)?.label ?? `近 ${days} 天`;

  return (
    <Space className="zw-dashboard" orientation="vertical" size={18} style={{ display: 'flex' }}>
      <Tabs
        defaultActiveKey="metrics"
        items={[
          {
            key: 'metrics',
            label: '经营指标',
            children: (
              <Space orientation="vertical" size={18} style={{ display: 'flex' }}>
                <Card className="zw-summary-card" styles={{ body: { padding: 0 } }}>
                  <div className="zw-summary-head">
                    <div>
                      <span className="zw-kicker">运营概览</span>
                      <h2>{rangeLabel}供餐与营养</h2>
                    </div>
                    <Segmented
                      options={RANGE_OPTIONS.map((option) => ({
                        label: option.label,
                        value: option.value,
                      }))}
                      value={days}
                      onChange={(value) => setDays(Number(value))}
                    />
                  </div>

                  <div className="zw-metric-grid">
                    <Metric
                      label="平均每餐人次"
                      value={summary.data?.avg_diner_count.toLocaleString('zh-CN') ?? '—'}
                      unit="人次"
                      hint="按每个餐次统计"
                      loading={summary.isPending}
                      lead
                    />
                    <Metric
                      label="人均食盐"
                      value={trimDecimal(summary.data?.avg_salt_per_capita_g)}
                      unit="克/日"
                      hint="每日不超过 5 克"
                      loading={summary.isPending}
                      lead
                    />
                    <Metric
                      label="人均烹调油"
                      value={trimDecimal(summary.data?.avg_oil_per_capita_g)}
                      unit="克/日"
                      hint="每日 25 ~ 30 克"
                      loading={summary.isPending}
                      lead
                    />
                    <Metric
                      label="最近一日达标率"
                      value={formatPercent(summary.data?.latest_compliance_rate)}
                      hint="最近一条核算记录"
                      loading={summary.isPending}
                      lead
                    />
                    <Metric
                      label="人均添加糖"
                      value={trimDecimal(summary.data?.avg_added_sugar_per_capita_g)}
                      unit="克/日"
                      hint="每日不超过 50 克"
                      loading={summary.isPending}
                    />
                    <Metric
                      label="平均浪费率"
                      value={formatPercent(summary.data?.avg_waste_ratio)}
                      hint="剩餐量占供餐量"
                      loading={summary.isPending}
                    />
                    <Metric
                      label="每日食物种类"
                      value={trimDecimal(summary.data?.avg_dish_variety)}
                      unit="种"
                      hint="每日不少于 12 种"
                      loading={summary.isPending}
                    />
                    <Metric
                      label="有记录天数"
                      value={summary.data?.days_with_records ?? 0}
                      unit="天"
                      hint={rangeLabel}
                      loading={summary.isPending}
                    />
                  </div>
                </Card>

                <Row gutter={[18, 18]}>
                  <Col xs={24} xl={14}>
                    <Card
                      className="zw-chart-card"
                      title="油盐糖用量趋势"
                      extra={<span className="zw-chart-hint">餐次总量 · 克</span>}
                    >
                      {trends.isPending ? (
                        <Skeleton active />
                      ) : (
                        <>
                          <EChart
                            height={300}
                            ariaLabel="油盐糖每日用量趋势图"
                            option={buildTrendOption(trends.data)}
                          />
                          <Typography.Paragraph className="zw-chart-note">
                            注：这里统计的是当餐全部就餐人次的总量，与「每人每日」的基准不是同一量纲，
                            因此不在此图直接画目标线；达标判断以右侧「人均摄入与推荐值」为准。
                          </Typography.Paragraph>
                        </>
                      )}
                    </Card>
                  </Col>
                  <Col xs={24} xl={10}>
                    <Card
                      className="zw-chart-card"
                      title="人均摄入与推荐值"
                      extra={<span className="zw-chart-hint">每人每日</span>}
                    >
                      {perCapita.isPending ? (
                        <Skeleton active />
                      ) : (
                        <div className="zw-compare">
                          <Typography.Paragraph className="zw-compare-note">
                            {perCapita.data?.basis_note}
                          </Typography.Paragraph>
                          <Table<StandardComparison>
                            rowKey="code"
                            size="small"
                            pagination={false}
                            dataSource={perCapita.data?.comparisons ?? []}
                            columns={comparisonColumns}
                          />
                        </div>
                      )}
                    </Card>
                  </Col>
                </Row>

                <Row gutter={[18, 18]}>
                  <Col xs={24} xl={12}>
                    <Card
                      className="zw-chart-card"
                      title="营养达标率"
                      extra={<span className="zw-chart-hint">每日核算</span>}
                    >
                      {compliance.isPending ? (
                        <Skeleton active />
                      ) : (
                        <EChart
                          height={280}
                          ariaLabel="每日营养达标率图"
                          option={buildComplianceOption(compliance.data)}
                        />
                      )}
                    </Card>
                  </Col>
                  <Col xs={24} xl={12}>
                    <Card
                      className="zw-chart-card"
                      title="剩餐量与浪费率"
                      extra={<span className="zw-chart-hint">浪费率 / 千克</span>}
                    >
                      {waste.isPending ? (
                        <Skeleton active />
                      ) : (
                        <EChart
                          height={280}
                          ariaLabel="每日剩餐量与浪费率图"
                          option={buildWasteOption(waste.data)}
                        />
                      )}
                    </Card>
                  </Col>
                </Row>
              </Space>
            ),
          },
          {
            key: 'menus',
            label: '今明菜单',
            children: <MenuOverview />,
          },
        ]}
      />
    </Space>
  );
}

const comparisonColumns: TableProps<StandardComparison>['columns'] = [
  { title: '指标', dataIndex: 'label', width: 100 },
  {
    title: '实际',
    dataIndex: 'actual',
    width: 98,
    align: 'right',
    render: (value: string | null, record) =>
      value === null ? '—' : `${trimDecimal(value)} ${record.unit}`,
  },
  {
    title: '推荐',
    key: 'target',
    render: (_, record) => {
      const min = trimDecimal(record.target_min);
      const max = trimDecimal(record.target_max);
      if (record.target_min && record.target_max) return `${min} ~ ${max} ${record.unit}`;
      if (record.target_max) return `≤ ${max} ${record.unit}`;
      if (record.target_min) return `≥ ${min} ${record.unit}`;
      return '—';
    },
  },
  {
    title: '结论',
    dataIndex: 'status',
    width: 96,
    align: 'center',
    render: (status: string) => (
      <Tag variant="filled" color={STATUS_COLOR[status] ?? 'default'}>
        {STATUS_TEXT[status] ?? status}
      </Tag>
    ),
  },
];

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

function buildTrendOption(data?: TrendsResponse): EChartOption {
  const points = data?.points ?? [];
  const dates = points.map((point) => point.date.slice(5));

  return {
    textStyle: chartTextStyle,
    color: [CHART_GREEN, CHART_AMBER, CHART_SAGE],
    tooltip: { ...tooltipBase, trigger: 'axis' },
    // 图例放顶部：默认的底部居中被横轴日期标签压住，读起来很挤
    legend: { ...legendBase, data: ['食用油', '食盐', '添加糖'] },
    grid: { left: 56, right: 18, top: 44, bottom: 30 },
    xAxis: { ...xAxisBase, data: dates, boundaryGap: false },
    yAxis: { ...yAxisBase, name: '克', nameTextStyle: { color: CHART_MUTED, fontSize: 11 } },
    series: [
      {
        name: '食用油',
        type: 'line',
        smooth: 0.35,
        showSymbol: false,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { width: 2.4 },
        areaStyle: { opacity: 0.08 },
        data: points.map((point) => toNumber(point.oil_total_g)),
      },
      {
        name: '食盐',
        type: 'line',
        smooth: 0.35,
        showSymbol: false,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { width: 2.4 },
        areaStyle: { opacity: 0.06 },
        data: points.map((point) => toNumber(point.salt_total_g)),
      },
      {
        name: '添加糖',
        type: 'line',
        smooth: 0.35,
        showSymbol: false,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { width: 2 },
        data: points.map((point) => toNumber(point.sugar_total_g)),
      },
    ],
  };
}

function buildComplianceOption(data?: ComplianceResponse): EChartOption {
  const points = data?.points ?? [];

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
        data: points.map((point) => toNumber(point.rate, 4)),
      },
    ],
  };
}

function buildWasteOption(data?: WasteResponse): EChartOption {
  const points = data?.points ?? [];

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
        data: points.map((point) => toNumber(point.waste_ratio, 4)),
      },
      {
        name: '剩餐量',
        type: 'line',
        smooth: 0.35,
        showSymbol: false,
        lineStyle: { width: 2.4, color: CHART_GREEN },
        itemStyle: { color: CHART_GREEN },
        yAxisIndex: 1,
        data: points.map((point) => toNumber(point.leftover_weight_g) / 1000),
      },
    ],
  };
}

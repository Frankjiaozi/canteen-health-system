import {
  Card,
  Col,
  Row,
  Segmented,
  Skeleton,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
} from 'antd';
import type { TableProps } from 'antd';
import { useState } from 'react';
import { EChart, type EChartOption } from '@/shared/components/EChart';
import { useDashboard } from '../hooks/useDashboard';
import { RANGE_OPTIONS, formatPercent, toNumber, trimDecimal } from '../lib/format';
import type {
  ComplianceResponse,
  StandardComparison,
  TrendsResponse,
  WasteResponse,
} from '../types';

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

export function DashboardPage() {
  const [days, setDays] = useState<number>(14);
  const { summary, trends, perCapita, compliance, waste } = useDashboard(days);

  return (
    <Space orientation="vertical" size={16} style={{ display: 'flex' }}>
      <Card
        title="数据看板"
        extra={
          <Segmented
            options={RANGE_OPTIONS.map((option) => ({ label: option.label, value: option.value }))}
            value={days}
            onChange={(value) => setDays(Number(value))}
          />
        }
      >
        <Row gutter={[16, 16]}>
          <Col xs={12} md={6}>
            <Statistic
              title="平均每餐人次"
              value={summary.data?.avg_diner_count ?? 0}
              loading={summary.isPending}
            />
          </Col>
          <Col xs={12} md={6}>
            <Statistic
              title="人均食盐（克/日）"
              value={trimDecimal(summary.data?.avg_salt_per_capita_g)}
              loading={summary.isPending}
            />
          </Col>
          <Col xs={12} md={6}>
            <Statistic
              title="人均烹调油（克/日）"
              value={trimDecimal(summary.data?.avg_oil_per_capita_g)}
              loading={summary.isPending}
            />
          </Col>
          <Col xs={12} md={6}>
            <Statistic
              title="最近一日达标率"
              value={formatPercent(summary.data?.latest_compliance_rate)}
              loading={summary.isPending}
            />
          </Col>
          <Col xs={12} md={6}>
            <Statistic
              title="人均添加糖（克/日）"
              value={trimDecimal(summary.data?.avg_added_sugar_per_capita_g)}
              loading={summary.isPending}
            />
          </Col>
          <Col xs={12} md={6}>
            <Statistic
              title="平均浪费率"
              value={formatPercent(summary.data?.avg_waste_ratio)}
              loading={summary.isPending}
            />
          </Col>
          <Col xs={12} md={6}>
            <Statistic
              title="每日食物种类数"
              value={trimDecimal(summary.data?.avg_dish_variety)}
              loading={summary.isPending}
            />
          </Col>
          <Col xs={12} md={6}>
            <Statistic
              title="有记录天数"
              value={summary.data?.days_with_records ?? 0}
              loading={summary.isPending}
            />
          </Col>
        </Row>
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={14}>
          <Card title="油盐糖用量趋势" size="small">
            {trends.isPending ? (
              <Skeleton active />
            ) : (
              <EChart
                height={320}
                ariaLabel="油盐糖每日用量趋势图"
                option={buildTrendOption(trends.data)}
              />
            )}
          </Card>
        </Col>
        <Col xs={24} xl={10}>
          <Card title="人均摄入与推荐值" size="small">
            {perCapita.isPending ? (
              <Skeleton active />
            ) : (
              <Space orientation="vertical" size={12} style={{ display: 'flex' }}>
                <Typography.Text type="secondary">{perCapita.data?.basis_note}</Typography.Text>
                <Table<StandardComparison>
                  rowKey="code"
                  size="small"
                  pagination={false}
                  dataSource={perCapita.data?.comparisons ?? []}
                  columns={comparisonColumns}
                />
              </Space>
            )}
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <Card title="营养达标率" size="small">
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
          <Card title="剩餐量与浪费率" size="small">
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
  );
}

const comparisonColumns: TableProps<StandardComparison>['columns'] = [
  { title: '指标', dataIndex: 'label', width: 110 },
  {
    title: '实际',
    dataIndex: 'actual',
    width: 100,
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
    width: 100,
    render: (status: string) => (
      <Tag color={STATUS_COLOR[status] ?? 'default'}>{STATUS_TEXT[status] ?? status}</Tag>
    ),
  },
];

function buildTrendOption(data?: TrendsResponse): EChartOption {
  const points = data?.points ?? [];
  const dates = points.map((point) => point.date.slice(5));
  const saltTarget = data?.targets.find((target) => target.code === 'SALT');
  const oilTarget = data?.targets.find((target) => target.code === 'EDIBLE_OIL');

  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['食用油', '食盐', '添加糖'] },
    grid: { left: 56, right: 24, top: 40, bottom: 32 },
    xAxis: { type: 'category', data: dates },
    yAxis: { type: 'value', name: '克' },
    series: [
      {
        name: '食用油',
        type: 'line',
        smooth: true,
        data: points.map((point) => toNumber(point.oil_total_g)),
      },
      {
        name: '食盐',
        type: 'line',
        smooth: true,
        data: points.map((point) => toNumber(point.salt_total_g)),
      },
      {
        name: '添加糖',
        type: 'line',
        smooth: true,
        data: points.map((point) => toNumber(point.sugar_total_g)),
      },
    ],
    // 这里画的是当餐总量，与「人均/日」的基准不是一个量纲，因此不画目标线。
    // 达标判断统一放在「人均摄入与推荐值」那栏，避免在图上直接比出错误结论。
    ...(saltTarget || oilTarget
      ? {
          title: {
            text: '注：总量按当餐全部就餐人次统计，达标判断以「人均摄入与推荐值」为准',
            left: 0,
            top: 0,
            textStyle: { fontSize: 12, fontWeight: 'normal', color: '#8c8c8c' },
          },
        }
      : {}),
  };
}

function buildComplianceOption(data?: ComplianceResponse): EChartOption {
  const points = data?.points ?? [];

  return {
    tooltip: {
      trigger: 'axis',
      valueFormatter: (value: unknown) =>
        typeof value === 'number' ? `${(value * 100).toFixed(1)}%` : String(value),
    },
    grid: { left: 56, right: 24, top: 24, bottom: 32 },
    xAxis: { type: 'category', data: points.map((point) => point.date.slice(5)) },
    yAxis: { type: 'value', max: 1, name: '达标率', axisLabel: { formatter: '{value}' } },
    series: [
      {
        name: '达标率',
        type: 'bar',
        data: points.map((point) => toNumber(point.rate, 4)),
        itemStyle: { color: '#1677ff' },
      },
    ],
  };
}

function buildWasteOption(data?: WasteResponse): EChartOption {
  const points = data?.points ?? [];

  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['浪费率', '剩餐量'] },
    grid: { left: 56, right: 56, top: 40, bottom: 32 },
    xAxis: { type: 'category', data: points.map((point) => point.date.slice(5)) },
    yAxis: [
      { type: 'value', name: '浪费率', max: 1 },
      { type: 'value', name: '千克', position: 'right' },
    ],
    series: [
      {
        name: '浪费率',
        type: 'bar',
        data: points.map((point) => toNumber(point.waste_ratio, 4)),
        itemStyle: { color: '#faad14' },
      },
      {
        name: '剩餐量',
        type: 'line',
        smooth: true,
        yAxisIndex: 1,
        data: points.map((point) => toNumber(point.leftover_weight_g) / 1000),
        itemStyle: { color: '#13c2c2' },
      },
    ],
  };
}

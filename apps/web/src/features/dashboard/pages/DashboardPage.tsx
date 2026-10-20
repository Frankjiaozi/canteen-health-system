import { calendarRows } from '../lib/calendar';
import {
  Alert,
  Card,
  Col,
  Row,
  Segmented,
  Skeleton,
  Space,
  Tabs,
  Tag,
  Typography,
  Progress,
  Popover,
} from 'antd';
import { useState, type ReactNode } from 'react';
import { EChart } from '@/shared/components/EChart';
import { MenuOverview } from '../components/MenuOverview';
import { DashboardMenuPreview } from '../components/DashboardMenuPreview';
import CountUp from '@/shared/components/react-bits/CountUp';
import {
  FireOutlined,
  AppstoreOutlined,
  TeamOutlined,
  ExperimentOutlined,
  DeleteOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import { useDashboard } from '../hooks/useDashboard';
import { RANGE_OPTIONS, formatPercent, toNumber, trimDecimal } from '../lib/format';
import type { StandardComparison } from '../types';
import { buildTrendOption, buildComplianceOption, buildWasteOption } from '../lib/charts';
import './dashboard.css';
import './reference-dashboard.css';

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

interface MetricProps {
  label: string;
  value: ReactNode;
  unit?: string;
  hint?: string;
  loading?: boolean;
  lead?: boolean;
}

function Metric({ label, value, unit, hint, loading, lead }: MetricProps) {
  const text = typeof value === 'number' || typeof value === 'string' ? String(value) : '';
  const numeric = /^\d[\d,.]*%?$/.test(text);
  return (
    <div className={`zw-metric${lead ? ' is-lead' : ''}`}>
      <span className="zw-metric-label">{label}</span>
      {loading ? (
        <Skeleton.Button active size="small" className="zw-metric-skeleton" />
      ) : (
        <span className="zw-metric-value">
          {numeric ? (
            <CountUp
              key={text}
              to={Number(text.replaceAll(',', '').replace('%', ''))}
              decimals={(text.replace('%', '').split('.')[1] ?? '').length}
              separator=","
              suffix={text.endsWith('%') ? '%' : ''}
              trigger="load"
              duration={0.65}
            />
          ) : (
            value
          )}
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
        defaultActiveKey="home"
        items={[
          {
            key: 'home',
            label: '膳食总览',
            children: <ReferenceOverview days={days} setDays={setDays} />,
          },
          {
            key: 'metrics',
            label: '营养分析',
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

                  <div className="zw-summary-body">
                    <div className="zw-metric-grid">
                      <Metric
                        label="平均每日供餐人次"
                        value={summary.data?.avg_diner_count?.toLocaleString('zh-CN') ?? '—'}
                        unit="人次"
                        hint="已记录日期的每日合计均值"
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
                        label="平均浪费率"
                        value={formatPercent(summary.data?.avg_waste_ratio)}
                        hint="剩餐量占供餐量"
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
                        label="最近核算日期"
                        value={perCapita.data?.latest_date?.slice(5) ?? '—'}
                        hint="来自实际核算记录"
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
                    <div className="zw-summary-ring">
                      <Progress
                        type="dashboard"
                        percent={Math.max(
                          0,
                          Math.min(100, Number(summary.data?.latest_compliance_rate ?? 0) * 100),
                        )}
                        strokeColor="#809574"
                        railColor="#ebe7da"
                        size={128}
                        strokeWidth={7}
                        format={() => (
                          <div className="zw-ring-label">
                            <strong>{formatPercent(summary.data?.latest_compliance_rate)}</strong>
                            <span>最近一日达标率</span>
                          </div>
                        )}
                      />
                      <span>依据最近一条核算记录</span>
                    </div>
                  </div>
                </Card>

                <Row gutter={[18, 18]}>
                  <Col xs={24} xl={14}>
                    <Card
                      className="zw-chart-card"
                      title="油盐糖用量趋势"
                      extra={<span className="zw-chart-hint">每日总量 · 克</span>}
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
                          <Popover
                            title="数据口径"
                            content={
                              <p style={{ maxWidth: 320 }}>
                                趋势图为每日总量，人均推荐值按每人每日展示，两者不能直接比较。
                              </p>
                            }
                          >
                            <span className="zw-chart-caliber">
                              <InfoCircleOutlined /> 每日总量，与每人每日基准不同
                            </span>
                          </Popover>
                          <Typography.Paragraph className="zw-chart-note" hidden>
                            注：这里统计的是当日已记录餐次的调料总量，与「每人每日」的基准不是同一量纲，
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
                          <Popover
                            title="数值口径"
                            content={<p style={{ maxWidth: 360 }}>{perCapita.data?.basis_note}</p>}
                          >
                            <span className="zw-chart-caliber">
                              <InfoCircleOutlined /> 查看来源与核算口径
                            </span>
                          </Popover>
                          <ComparisonRows items={perCapita.data?.comparisons ?? []} />
                        </div>
                      )}
                    </Card>
                  </Col>
                </Row>

                <DashboardMenuPreview />
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

function ReferenceOverview({ days, setDays }: { days: number; setDays: (value: number) => void }) {
  const { summary, trends, perCapita, waste } = useDashboard(days);
  const comparisons = perCapita.data?.comparisons ?? [];
  const known = comparisons.filter((item) => item.status !== 'unknown');
  const passed = known.filter((item) => item.status === 'ok').length;
  const metrics = [
    {
      label: '平均每日供餐人次',
      value: summary.data?.avg_diner_count?.toLocaleString('zh-CN') ?? '—',
      unit: '人次',
      icon: <TeamOutlined />,
      hint: '每日人次合计的均值',
      points: calendarRows(trends.data).map(({ point }) => point?.diner_count ?? null),
      sparkLabel: '每日供餐人次',
      color: '#789775',
    },
    {
      label: '人均食盐用量',
      value: trimDecimal(summary.data?.avg_salt_per_capita_g),
      unit: '克/日',
      icon: <ExperimentOutlined />,
      hint: '每日参考上限 5 克',
      points: calendarRows(trends.data).map(({ point }) => toNumber(point?.salt_per_capita_g)),
      sparkLabel: '每日人均食盐',
      color: '#b7a27b',
    },
    {
      label: '平均浪费率',
      value: formatPercent(summary.data?.avg_waste_ratio),
      unit: '',
      icon: <DeleteOutlined />,
      hint: '剩餐量占供餐量',
      points: calendarRows(waste.data).map(({ point }) => toNumber(point?.waste_ratio, 4)),
      sparkLabel: '每日浪费率',
      color: '#ce927a',
    },
  ];
  return (
    <div className="zw-reference-grid">
      {(summary.isError || trends.isError || perCapita.isError || waste.isError) && (
        <Alert
          className="zw-data-note"
          type="error"
          title="部分数据读取失败，请刷新重试；未读取的数据不代表零值或达标。"
        />
      )}
      <div className="zw-data-note">
        {trends.data
          ? `${trends.data.start} 至 ${trends.data.end}（含首尾，共 ${trends.data.days} 天） · ${summary.data?.days_with_records ?? '—'} 天有采集记录；缺记录留空，均值仅按已记录数据计算。`
          : '正在读取统计范围…'}
      </div>
      <section className="zw-reference-metrics">
        {metrics.map((metric) => (
          <div className="zw-reference-metric" key={metric.label}>
            <span className="zw-reference-icon">{metric.icon}</span>
            <div>
              <Metric
                label={metric.label}
                value={metric.value}
                unit={metric.unit}
                hint={metric.hint}
                loading={summary.isPending}
              />
              <div className="zw-mini-history">
                {metric.points?.length ? (
                  <>
                    <Sparkline values={metric.points} color={metric.color} />
                    <small>{metric.sparkLabel}</small>
                  </>
                ) : (
                  <span>统计范围：近 {days} 天</span>
                )}
              </div>
            </div>
          </div>
        ))}
      </section>
      <section className="zw-reference-nutrition">
        <h2>
          营养达标情况{' '}
          <Popover content="依据最近一日的人均摄入核算结果；每项指标等权统计。">
            <InfoCircleOutlined />
          </Popover>
        </h2>
        <div className="zw-reference-caption">
          最近记录：{perCapita.data?.latest_date ?? '暂无'}（已记录餐次）
        </div>
        <div className="zw-nutrition-body">
          <Progress
            type="circle"
            size={118}
            strokeWidth={14}
            percent={known.length ? (passed / known.length) * 100 : 0}
            strokeColor="#789775"
            railColor="#e8dac4"
            format={() => (
              <span>
                <strong>
                  {known.length ? passed : '—'}
                  {known.length > 0 && <small> / {known.length}</small>}
                </strong>
                <em>{known.length ? '指标达标' : '暂无核算'}</em>
              </span>
            )}
          />
          <ul>
            {comparisons.slice(0, 4).map((item) => (
              <li key={item.code}>
                <i style={{ background: item.status === 'ok' ? '#8fa489' : '#ceb994' }} />
                {item.label}
                <span>{STATUS_TEXT[item.status]}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>
      <section className="zw-reference-trend">
        <header>
          <h2>油盐糖用量趋势</h2>
          <Segmented
            options={RANGE_OPTIONS.map((option) => ({ label: option.label, value: option.value }))}
            value={days}
            onChange={(v) => setDays(Number(v))}
          />
        </header>
        <span className="zw-reference-caption">每日总量 · 克</span>
        {trends.isPending ? (
          <Skeleton active />
        ) : (
          <EChart
            height={200}
            ariaLabel="油盐糖每日用量趋势图"
            option={buildTrendOption(trends.data)}
          />
        )}
      </section>
      <section className="zw-reference-comparison">
        <header>
          <h2>人均每日参考</h2>
          <Popover content={<p style={{ maxWidth: 320 }}>{perCapita.data?.basis_note}</p>}>
            <span className="zw-reference-caption">
              核算口径 <InfoCircleOutlined />
            </span>
          </Popover>
        </header>
        <p className="zw-reference-caption">
          最近记录：{perCapita.data?.latest_date ?? '暂无'} · 非期间平均值
        </p>
        <ComparisonRows
          items={comparisons
            .filter((item) => item.code !== 'dish_variety' && !item.label.includes('种类'))
            .slice(0, 3)}
        />
      </section>
      <div className="zw-reference-bottom">
        <DashboardMenuPreview />
      </div>
    </div>
  );
}

function Sparkline({ values, color }: { values: (number | null)[]; color: string }) {
  const valid = values.filter((value): value is number => value !== null && Number.isFinite(value));
  if (!valid.length) return <span>暂无记录</span>;
  const min = Math.min(...valid);
  const span = Math.max(...valid) - min || 1;
  const segments: string[][] = [];
  let segment: string[] = [];
  values.forEach((value, index) => {
    if (value === null || !Number.isFinite(value)) {
      if (segment.length) segments.push(segment);
      segment = [];
      return;
    }
    segment.push(
      `${(index / Math.max(1, values.length - 1)) * 170},${35 - ((value - min) / span) * 27}`,
    );
  });
  if (segment.length) segments.push(segment);
  return (
    <svg viewBox="0 0 170 44" aria-hidden="true">
      {segments.map((points, index) => (
        <g key={index}>
          <polyline
            points={points.join(' ')}
            fill="none"
            stroke={color}
            strokeWidth="1.7"
            strokeLinejoin="round"
          />
          {points.map((point) => (
            <circle
              key={point}
              cx={point.split(',')[0]}
              cy={point.split(',')[1]}
              r="1.6"
              fill={color}
            />
          ))}
        </g>
      ))}
    </svg>
  );
}

function ComparisonRows({ items }: { items: StandardComparison[] }) {
  if (!items.length) return <p className="zw-chart-note">暂无核算结果</p>;
  return (
    <div className="zw-comparison-rows">
      {items.map((item) => {
        const ceiling = Number(item.target_max ?? item.target_min);
        // 只画相对参考值的长度；判定与推荐范围仍直接来自业务 API。
        const percent =
          item.actual != null && ceiling > 0
            ? Math.min(100, Math.max(0, (Number(item.actual) / ceiling) * 100))
            : 0;
        const target =
          item.target_min != null && item.target_max != null
            ? `${trimDecimal(item.target_min)} ~ ${trimDecimal(item.target_max)}`
            : item.target_max != null
              ? `≤ ${trimDecimal(item.target_max)}`
              : item.target_min != null
                ? `≥ ${trimDecimal(item.target_min)}`
                : '—';
        return (
          <div className="zw-comparison-row" key={item.code}>
            <div>
              <span className="zw-reference-row-icon" aria-hidden="true">
                {item.label.includes('油') ? (
                  <FireOutlined />
                ) : item.label.includes('盐') ? (
                  <ExperimentOutlined />
                ) : (
                  <AppstoreOutlined />
                )}
              </span>
              <strong>{item.label}</strong>
              <span>
                {trimDecimal(item.actual)} <small>{item.unit}</small>
              </span>
            </div>
            <Progress
              percent={percent}
              showInfo={false}
              strokeColor={
                item.status === 'over' ? '#bc7d68' : item.status === 'under' ? '#b3a075' : '#8fa181'
              }
              railColor="#efebe2"
              strokeWidth={7}
            />
            <footer>
              <span>
                参考 {target} {item.unit}
              </span>
              <Tag color={STATUS_COLOR[item.status] ?? 'default'}>
                {STATUS_TEXT[item.status] ?? item.status}
              </Tag>
            </footer>
          </div>
        );
      })}
    </div>
  );
}

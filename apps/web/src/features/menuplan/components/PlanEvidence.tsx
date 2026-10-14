import { Card, Collapse, Space, Table, Tag, Typography } from 'antd';
import dayjs from 'dayjs';
import { HolidayTable } from '@/features/forecast/components/HolidayTable';
import { useBacktest } from '@/features/forecast/hooks/useForecast';
import { describeCoverage, describeMape } from '@/features/forecast/lib/format';
import { useSuggestionHistory } from '@/features/recommendation/hooks/useRecommendation';
import { decisionLabel } from '@/features/recommendation/lib/present';
import { describePredictionOrigin } from '../lib/present';
import type { MealType, MenuPlanDish, MenuPlanResponse, SuggestionSummary } from '../types';

const BACKTEST_DAYS = 56;
const DECISION_COLOR = { ok: 'green', bad: 'red', pending: 'default' } as const;

/**
 * ③ 依据与校验——默认折叠。
 *
 * 日常点一次按钮不需要看到这些；但「为什么是这个数」必须查得到，
 * 所以每道菜的份数依据、回测误差、日历都在这里，而不是被删掉。
 */
export function PlanEvidence({ plan }: { plan: MenuPlanResponse }) {
  const mealType: MealType = plan.meal_type;
  const backtest = useBacktest(BACKTEST_DAYS, mealType);
  const history = useSuggestionHistory(plan.date);
  const verdict = backtest.data
    ? describeMape(backtest.data.mape, backtest.data.target_mape)
    : null;

  return (
    <Collapse
      style={{ marginTop: 16 }}
      items={[
        {
          key: 'evidence',
          label: `③ 依据与校验（${plan.dishes.length} 道菜的份数依据、回测误差、节假日日历）`,
          children: (
            <Space orientation="vertical" size={16} style={{ width: '100%' }}>
              <Card size="small" title="每道菜的份数与依据">
                <Table<MenuPlanDish>
                  rowKey="dish_id"
                  size="small"
                  pagination={false}
                  dataSource={plan.dishes}
                  columns={[
                    { title: '菜品', dataIndex: 'dish_name', width: 180 },
                    {
                      title: '这份采购量用的份数',
                      width: 300,
                      render: (_, dish) => {
                        const origin = describePredictionOrigin(dish);
                        return (
                          <Typography.Text
                            type={origin.tone === 'fallback' ? 'warning' : undefined}
                          >
                            {origin.text}
                          </Typography.Text>
                        );
                      },
                    },
                    {
                      title: '单份营养取自',
                      render: (_, dish) =>
                        dish.prediction_fallback ? (
                          <Typography.Text type="secondary">
                            8 周内样本不足，份数给不出数字，按「每人一份」估
                          </Typography.Text>
                        ) : (
                          <Tag>{dish.nutrition_basis || '—'}</Tag>
                        ),
                    },
                  ]}
                />
                {plan.calendar_notes.length > 0 ? (
                  <Space style={{ marginTop: 12 }} wrap>
                    {plan.calendar_notes.map((note) => (
                      <Tag key={note} color="orange">
                        {note}
                      </Tag>
                    ))}
                  </Space>
                ) : null}
                {plan.skipped_predictions.length > 0 ? (
                  <Typography.Paragraph type="secondary" style={{ marginTop: 12 }}>
                    历史不足、这次没有预测的菜：{plan.skipped_predictions.join('、')}
                  </Typography.Paragraph>
                ) : null}
              </Card>

              {backtest.data && verdict ? (
                <Card size="small" title="回测：这套算法在历史上有多准">
                  <Space orientation="vertical" size={4}>
                    <Space>
                      <Tag color={verdict.ok ? 'green' : 'red'}>
                        {verdict.ok ? '达标' : '不达标'}
                      </Tag>
                      <Typography.Text>{verdict.text}</Typography.Text>
                    </Space>
                    <Typography.Text type="secondary">
                      {describeCoverage(backtest.data.usable_days, backtest.data.days)}。
                      {backtest.data.note}
                    </Typography.Text>
                  </Space>
                </Card>
              ) : null}

              {history.data && history.data.length > 0 ? (
                <Card size="small" title={`${plan.date} 当天的菜单记录`}>
                  <Table<SuggestionSummary>
                    rowKey="id"
                    size="small"
                    pagination={false}
                    dataSource={history.data}
                    columns={[
                      {
                        title: '结论',
                        width: 110,
                        render: (_, row) => {
                          const decision = decisionLabel(row.status);
                          return <Tag color={DECISION_COLOR[decision.tone]}>{decision.text}</Tag>;
                        },
                      },
                      { title: '道数', dataIndex: 'dish_count', width: 80, align: 'right' },
                      {
                        title: '成本（元）',
                        dataIndex: 'cost_estimate',
                        width: 110,
                        align: 'right',
                      },
                      {
                        title: '生成时间',
                        dataIndex: 'created_at',
                        width: 150,
                        render: (value: string) => dayjs(value).format('MM-DD HH:mm'),
                      },
                      {
                        title: '否决原因',
                        render: (_, row) =>
                          row.rejected_reason ?? (
                            <Typography.Text type="secondary">—</Typography.Text>
                          ),
                      },
                    ]}
                  />
                </Card>
              ) : null}

              <HolidayTable year={Number(plan.date.slice(0, 4))} />
            </Space>
          ),
        },
      ]}
    />
  );
}

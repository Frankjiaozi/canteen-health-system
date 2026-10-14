import { Button, Card, DatePicker, Segmented, Space, Table, Tag, Typography } from 'antd';
import dayjs from 'dayjs';
import { canWriteBusinessData } from '@/features/auth/lib/permissions';
import { useCurrentUser } from '@/features/auth/hooks/useAuth';
import { useDateMealSelection } from '@/shared/hooks/useDateMealSelection';
import { useEnumOptions } from '@/shared/hooks/useEnumOptions';
import { HolidayTable } from '../components/HolidayTable';
import { useBacktest, useRunForecast } from '../hooks/useForecast';
import {
  describeCoverage,
  describeDishBasis,
  describeMape,
  formatAmount,
  formatQuantity,
  formatServings,
} from '../lib/format';
import type { DishForecast, IngredientRequirement, MealType } from '../types';

const BACKTEST_DAYS = 56;

export function ForecastPage() {
  const { date: onDate, meal, setDate, setMeal } = useDateMealSelection('LUNCH');
  const mealType = meal as MealType;
  const { data: enumOptions } = useEnumOptions();
  const { data: user } = useCurrentUser();
  const canWrite = canWriteBusinessData(user);

  const runMutation = useRunForecast();
  const backtest = useBacktest(BACKTEST_DAYS, mealType);
  const result = runMutation.data;
  const verdict = backtest.data
    ? describeMape(backtest.data.mape, backtest.data.target_mape)
    : null;

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      <Card
        title="消耗量预测"
        extra={
          <Space>
            <DatePicker
              value={dayjs(onDate)}
              allowClear={false}
              onChange={(value) => value && setDate(value.format('YYYY-MM-DD'))}
            />
            <Segmented<MealType>
              value={mealType}
              onChange={(value) => setMeal(value)}
              options={(enumOptions?.meal_type ?? []).map((option) => ({
                value: option.value as MealType,
                label: option.label,
              }))}
            />
            {canWrite ? (
              <Button
                type="primary"
                loading={runMutation.isPending}
                onClick={() => runMutation.mutate({ onDate, mealType })}
              >
                生成预测
              </Button>
            ) : null}
          </Space>
        }
      >
        <Typography.Paragraph type="secondary">
          预测份数 = 最近 6 个同星期几的份数平均 × 日历修正系数。标了异常、临时替换与 份数为 0
          的日子不进历史序列；同星期样本不足时退化为「全期平均 × 星期几规律」， 并在依据一列写明。
        </Typography.Paragraph>

        {backtest.data && verdict ? (
          <Card size="small" style={{ marginBottom: 16 }}>
            <Space orientation="vertical" size={4}>
              <Space>
                <Typography.Text strong>回测</Typography.Text>
                <Tag color={verdict.ok ? 'green' : 'red'}>{verdict.ok ? '达标' : '不达标'}</Tag>
                <Typography.Text>{verdict.text}</Typography.Text>
              </Space>
              <Typography.Text type="secondary">
                {describeCoverage(backtest.data.usable_days, backtest.data.days)}。
                {backtest.data.note}
              </Typography.Text>
            </Space>
          </Card>
        ) : null}

        {result ? (
          <>
            <Space style={{ marginBottom: 12 }} wrap>
              <Typography.Text>
                采购建议依据：{result.basis_label}（{result.basis_date}）
              </Typography.Text>
              {result.calendar_notes.map((note) => (
                <Tag key={note} color="orange">
                  {note}
                </Tag>
              ))}
              {result.skipped.length > 0 ? (
                <Typography.Text type="secondary">
                  历史不足未预测：{result.skipped.join('、')}
                </Typography.Text>
              ) : null}
            </Space>

            <Table<DishForecast>
              rowKey="dish_id"
              size="small"
              pagination={false}
              scroll={{ y: 320 }}
              dataSource={result.dishes}
              columns={[
                {
                  title: '菜品',
                  width: 180,
                  render: (_, dish) => (
                    <Space size={6}>
                      <Typography.Text strong>{dish.dish_name}</Typography.Text>
                      {dish.planned ? <Tag color="blue">当天供应</Tag> : null}
                    </Space>
                  ),
                },
                { title: '类别', dataIndex: 'category_label', width: 90 },
                { title: '做法', dataIndex: 'cooking_method_label', width: 80 },
                {
                  title: '预测份数',
                  width: 110,
                  align: 'right',
                  render: (_, dish) => formatServings(dish.predicted_servings),
                },
                {
                  title: '置信区间',
                  width: 150,
                  align: 'right',
                  render: (_, dish) =>
                    `${formatServings(dish.ci_lower)} ~ ${formatServings(dish.ci_upper)}`,
                },
                {
                  title: '依据',
                  render: (_, dish) => (
                    <Typography.Text type="secondary">{describeDishBasis(dish)}</Typography.Text>
                  ),
                },
              ]}
            />

            <Card
              size="small"
              style={{ marginTop: 16 }}
              title={`采购建议单（共 ${result.requirements.length} 项）`}
              extra={
                <Typography.Text strong>
                  预计金额 {formatAmount(result.total_cost)} 元
                </Typography.Text>
              }
            >
              <Table<IngredientRequirement>
                rowKey="name"
                size="small"
                pagination={false}
                dataSource={result.requirements}
                columns={[
                  { title: '食材 / 调味料', dataIndex: 'name', width: 180 },
                  {
                    title: '建议采购量',
                    width: 150,
                    align: 'right',
                    render: (_, row) => `${formatQuantity(row.quantity)} ${row.unit}`,
                  },
                  {
                    title: '单价（元/公斤）',
                    width: 150,
                    align: 'right',
                    render: (_, row) =>
                      row.unit_price === null ? (
                        <Typography.Text type="secondary">未录入</Typography.Text>
                      ) : (
                        formatAmount(row.unit_price)
                      ),
                  },
                  {
                    title: '预计金额（元）',
                    width: 150,
                    align: 'right',
                    render: (_, row) => formatAmount(row.estimated_cost),
                  },
                ]}
              />
            </Card>
          </>
        ) : (
          <Typography.Text type="secondary">
            选好日期与餐次后点「生成预测」，这里会给出每道菜的份数与采购建议单。
          </Typography.Text>
        )}
      </Card>

      <HolidayTable year={Number(onDate.slice(0, 4))} />
    </Space>
  );
}

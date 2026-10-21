import { Alert, Card, Space, Table, Typography } from 'antd';
import { formatAmount, formatQuantity } from '@/features/forecast/lib/format';
import { summarizePurchase } from '../lib/present';
import type { IngredientRequirement, MenuPlanResponse } from '../types';

export function PurchaseTable({ requirements }: { requirements: IngredientRequirement[] }) {
  return (
    <Table<IngredientRequirement>
      rowKey="name"
      size="small"
      pagination={false}
      dataSource={requirements}
      columns={[
        {
          title: '排名',
          width: 70,
          align: 'right',
          render: (_, __, index) => index + 1,
        },
        { title: '食材 / 调味料', dataIndex: 'name', width: 180 },
        {
          title: '建议采购量',
          width: 150,
          align: 'right',
          render: (_, row) => `${formatQuantity(row.quantity)} ${row.unit}`,
        },
        {
          title: '单价（元/公斤市品）',
          width: 170,
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
          width: 140,
          align: 'right',
          render: (_, row) => formatAmount(row.estimated_cost),
        },
      ]}
    />
  );
}

/**
 * ② 明天要买多少料。
 *
 * 单子是按**预测份数**乘出来的，所以口径要写在标题下面（`servings_note`），
 * 每道菜用了多少份在③里逐条可查——两者分开写，是为了让这一节能直接打印给采购员。
 */
export function PurchaseList({
  plan,
  historical = false,
}: {
  plan: MenuPlanResponse;
  historical?: boolean;
}) {
  const summary = summarizePurchase(plan.requirements, plan.total_cost, plan.budget);
  const fallbackDishes = plan.dishes.filter((dish) => dish.prediction_fallback);

  return (
    <Card
      size="small"
      title={`② ${historical ? `${plan.date} 食材采购快照` : '明日食材采购建议'}（共 ${plan.requirements.length} 项）`}
      extra={
        <Typography.Text strong>
          采购金额 {formatAmount(plan.total_cost)} 元 / 预算 {formatAmount(plan.budget)} 元
        </Typography.Text>
      }
    >
      {summary.note ? (
        <Alert
          type={summary.tone === 'over' ? 'warning' : 'error'}
          showIcon
          style={{ marginBottom: 12 }}
          message={summary.tone === 'over' ? '采购金额超出预算' : '部分采购金额无法核算'}
          description={summary.note}
        />
      ) : null}

      {fallbackDishes.length > 0 ? (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message={`份数按每人一份估算：${fallbackDishes.map((dish) => dish.dish_name).join('、')}`}
        />
      ) : null}

      <PurchaseTable requirements={plan.requirements} />

      <Space style={{ marginTop: 12 }} wrap>
        <Typography.Text type="secondary">
          金额按「元/公斤市品」单价计。缺单价的项金额为空，合计因此偏低。
        </Typography.Text>
      </Space>
    </Card>
  );
}

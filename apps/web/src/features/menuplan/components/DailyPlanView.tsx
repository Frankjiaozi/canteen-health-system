import { Alert, Button, Card, Collapse, Space, Tag, Typography } from 'antd';
import { formatAmount } from '@/features/forecast/lib/format';
import { describeGap } from '@/features/recommendation/lib/present';
import type { DailyMenuPlanResponse } from '../types';
import type { DailySyncOutcome } from '../hooks/useMenuPlan';
import { summarizePurchase } from '../lib/present';
import { PurchaseTable } from './PurchaseList';

export function DailyPlanView({
  plan,
  canWrite,
  syncing,
  outcomes,
  onSync,
}: {
  plan: DailyMenuPlanResponse;
  canWrite: boolean;
  syncing: boolean;
  outcomes: DailySyncOutcome[] | null;
  onSync: () => void;
}) {
  const summary = summarizePurchase(plan.requirements, plan.total_cost, plan.budget);
  const fallbackDishes = plan.fallback_dishes ?? [];
  const syncedCount = outcomes?.filter((outcome) => outcome.ok).length ?? 0;
  const decision =
    syncedCount === plan.meals.length
      ? { text: '已同步', color: 'green' as const }
      : syncedCount > 0
        ? { text: '部分同步', color: 'orange' as const }
        : { text: '待确认', color: 'default' as const };
  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      <Card
        size="small"
        title={`① 明日三餐安排 · ${plan.date}`}
        extra={<Tag color={decision.color}>{decision.text}</Tag>}
      >
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
            gap: 12,
            marginTop: 16,
          }}
        >
          {plan.meals.map((meal) => (
            <Card
              key={meal.meal_type}
              size="small"
              title={`${meal.meal_type_label} · ${meal.diner_count} 人次`}
              extra={<Typography.Text strong>{formatAmount(meal.total_cost)} 元</Typography.Text>}
            >
              <Space orientation="vertical" size={8} style={{ width: '100%' }}>
                {meal.dishes.map((dish) => (
                  <div
                    key={dish.dish_id}
                    style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}
                  >
                    <span>{dish.dish_name}</span>
                    <Typography.Text type="secondary">
                      {formatAmount(dish.planned_servings ?? dish.predicted_servings)} 份
                    </Typography.Text>
                  </div>
                ))}
              </Space>
              <Typography.Paragraph type="secondary" style={{ margin: '12px 0 0' }}>
                {meal.gaps.filter((gap) => gap.status !== 'ok').length} 项营养偏差 · 预算{' '}
                {formatAmount(meal.budget)} 元
              </Typography.Paragraph>
            </Card>
          ))}
        </div>

        {canWrite ? (
          <Space
            wrap
            style={{
              width: '100%',
              marginTop: 16,
              paddingTop: 16,
              borderTop: '1px solid #f0f0f0',
            }}
          >
            <Button type="primary" loading={syncing} onClick={onSync}>
              {syncedCount === plan.meals.length ? '重新同步三餐' : '同步三餐至当日数据'}
            </Button>
            <Typography.Text type="secondary">
              按餐次分别校验；某餐已经录过采集时会跳过该餐，其余餐次继续写入。
            </Typography.Text>
          </Space>
        ) : null}

        {outcomes?.length ? (
          <Space orientation="vertical" size={8} style={{ width: '100%', marginTop: 12 }}>
            {outcomes.map((outcome) => (
              <Alert
                key={outcome.meal_type}
                type={outcome.ok ? 'success' : 'error'}
                showIcon
                message={`${outcome.meal_type_label}：${outcome.ok ? '已同步' : '未同步'}`}
                description={outcome.message}
              />
            ))}
          </Space>
        ) : null}
      </Card>

      <Card
        size="small"
        title={`② 全天食材采购建议（共 ${plan.requirements.length} 项）`}
        extra={
          <Typography.Text strong>
            采购金额 {formatAmount(plan.total_cost)} 元 / 预算 {formatAmount(plan.budget)} 元
          </Typography.Text>
        }
      >
        <Alert
          type={summary.tone === 'over' ? 'warning' : 'info'}
          showIcon
          style={{ marginBottom: 12 }}
          message={plan.servings_note}
          description={summary.note || '相同食材与调味料已合并，按金额从大到小排。'}
        />
        {fallbackDishes.length > 0 ? (
          <Alert
            type="warning"
            showIcon
            style={{ marginBottom: 12 }}
            message={`这些菜历史不足、预测不出份数，采购量按「每人一份」估算：${fallbackDishes.join('、')}`}
          />
        ) : null}
        <PurchaseTable requirements={plan.requirements} />
        <Typography.Paragraph type="secondary" style={{ margin: '12px 0 0' }}>
          金额按「元/公斤市品」单价计。缺单价的项金额为空，合计因此偏低。
        </Typography.Paragraph>
      </Card>

      <Collapse
        items={plan.meals.map((meal) => ({
          key: meal.meal_type,
          label: `${meal.meal_type_label}：${meal.gaps.filter((gap) => gap.status !== 'ok').length} 项偏差，${meal.reasons.length} 条推荐理由`,
          children: (
            <Space orientation="vertical" size={8} style={{ width: '100%' }}>
              {meal.gaps
                .filter((gap) => gap.status !== 'ok')
                .map((gap) => (
                  <Typography.Text key={gap.code}>
                    {gap.label}：{describeGap(gap)}
                  </Typography.Text>
                ))}
              {meal.reasons.map((reason) => (
                <Typography.Text key={`${reason.kind}-${reason.text}`} type="secondary">
                  {reason.text}
                </Typography.Text>
              ))}
            </Space>
          ),
        }))}
      />
    </Space>
  );
}

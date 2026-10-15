import { Button, Card, DatePicker, Empty, Segmented, Space, Typography } from 'antd';
import dayjs from 'dayjs';
import { useState } from 'react';
import { useCurrentUser } from '@/features/auth/hooks/useAuth';
import { canWriteBusinessData } from '@/features/auth/lib/permissions';
import { useSuggestionDetail } from '@/features/recommendation/hooks/useRecommendation';
import { useDateMealSelection } from '@/shared/hooks/useDateMealSelection';
import { useEnumOptions } from '@/shared/hooks/useEnumOptions';
import { PlanEvidence } from '../components/PlanEvidence';
import { PurchaseList } from '../components/PurchaseList';
import { RecommendedDishes } from '../components/RecommendedDishes';
import { useGenerateMenuPlan, useSyncMenuPlan } from '../hooks/useMenuPlan';
import type { MealType } from '../types';

/**
 * 明日菜单与采购。
 *
 * 这一页把原先的「菜单推荐」与「采购预测」合成一件事：明天做哪几道菜、要买多少料。
 * 分两页的时候，定完菜单还要再点一次才看得到采购量，而菜单本身又只在有份数时才算得准；
 * 合成一页之后，一次生成、一套份数、一张采购单。
 */
export function MenuPlanPage() {
  const tomorrow = dayjs().add(1, 'day').format('YYYY-MM-DD');
  const { date: onDate, meal, setDate, setMeal } = useDateMealSelection('LUNCH', tomorrow);
  const mealType = meal as MealType;
  const { data: enumOptions } = useEnumOptions();
  const { data: user } = useCurrentUser();
  const canWrite = canWriteBusinessData(user);

  const generate = useGenerateMenuPlan();
  const plan = generate.data ?? null;
  // 「已同步」只对**当前这一版**成立：换日期或重新生成之后，计划又变回未同步
  const [syncedId, setSyncedId] = useState<string | null>(null);
  // 结论（待确认 / 已采纳 / 已否决）是会变的，以详情查询为唯一来源；
  // 菜单内容本身来自生成结果——它不可变，没必要再查一次
  const suggestion = useSuggestionDetail(plan?.suggestion_id ?? null);
  const syncMutation = useSyncMenuPlan();
  const synced = plan !== null && syncedId === plan.suggestion_id;

  const handleGenerate = () => {
    setSyncedId(null);
    generate.mutate({ onDate, mealType });
  };

  const handleSync = () => {
    if (!plan) return;
    syncMutation.mutate(
      { onDate: plan.date, mealType: plan.meal_type, suggestionId: plan.suggestion_id },
      { onSuccess: () => setSyncedId(plan.suggestion_id) },
    );
  };

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      <Card
        title="明日菜单与采购"
        extra={
          <Space>
            <DatePicker
              value={dayjs(onDate)}
              allowClear={false}
              onChange={(value) => {
                if (value) {
                  setDate(value.format('YYYY-MM-DD'));
                  setSyncedId(null);
                }
              }}
            />
            <Segmented<MealType>
              value={mealType}
              onChange={(value) => {
                setMeal(value);
                setSyncedId(null);
              }}
              options={(enumOptions?.meal_type ?? []).map((option) => ({
                value: option.value as MealType,
                label: option.label,
              }))}
            />
            {canWrite ? (
              <Button type="primary" loading={generate.isPending} onClick={handleGenerate}>
                生成明日菜单
              </Button>
            ) : null}
          </Space>
        }
      >
        <Typography.Paragraph type="secondary">
          一次生成三件事：在营养目标下选出做哪几道菜 → 按同星期历史与节假日日历预测每道菜做多少份 →
          按各菜配方算出要买多少料。份数只有一套，采购量就是用它乘出来的。
        </Typography.Paragraph>

        {plan ? (
          <Space orientation="vertical" size={16} style={{ width: '100%' }}>
            <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
              {plan.notes.join('；')}
            </Typography.Paragraph>
            <RecommendedDishes
              plan={plan}
              suggestion={suggestion.data}
              synced={synced}
              syncing={syncMutation.isPending}
              onSync={handleSync}
            />
            <PurchaseList plan={plan} />
            <PlanEvidence plan={plan} />
          </Space>
        ) : (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              canWrite
                ? '选好日期与餐次后点「生成明日菜单」，这里会给出菜品、份数与采购建议。'
                : '菜单由食堂这边生成；生成后这里的每一栏你都能看到。'
            }
          />
        )}
      </Card>
    </Space>
  );
}

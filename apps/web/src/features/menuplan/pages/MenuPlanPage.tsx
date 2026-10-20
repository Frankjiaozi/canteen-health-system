import { Button, DatePicker, Empty, Segmented, Space, Typography } from 'antd';
import dayjs from 'dayjs';
import { useState } from 'react';
import { useCurrentUser } from '@/features/auth/hooks/useAuth';
import { canWriteBusinessData } from '@/features/auth/lib/permissions';
import { useSuggestionDetail } from '@/features/recommendation/hooks/useRecommendation';
import { useDateMealSelection } from '@/shared/hooks/useDateMealSelection';
import { useEnumOptions } from '@/shared/hooks/useEnumOptions';
import { PagePanel } from '@/shared/components/PagePanel';
import { DailyPlanView } from '../components/DailyPlanView';
import { PlanEvidence } from '../components/PlanEvidence';
import { PurchaseList } from '../components/PurchaseList';
import { RecommendedDishes } from '../components/RecommendedDishes';
import { BatchPlanner } from '../components/BatchPlanner';
import {
  useGenerateDailyMenuPlan,
  useGenerateMenuPlan,
  useSyncDailyMenuPlan,
  useSyncMenuPlan,
  type DailySyncOutcome,
} from '../hooks/useMenuPlan';
import type { DailyMenuPlanResponse, MealType } from '../types';
import './menuplan.css';

/**
 * 明日菜单与采购。
 *
 * 这一页把原先的「菜单推荐」与「采购预测」合成一件事：明天做哪几道菜、要买多少料。
 * 分两页的时候，定完菜单还要再点一次才看得到采购量，而菜单本身又只在有份数时才算得准；
 * 合成一页之后，一次生成、一套份数、一张采购单。
 *
 * 「单日」与「批量排菜单」是同一件事的两个粒度：出去吃一顿 vs 一次排一两个星期。
 * 放在同一页用模式切换，导航里就不必再多一个入口。
 */
export function MenuPlanPage() {
  const tomorrow = dayjs().add(1, 'day').format('YYYY-MM-DD');
  const { date: onDate, meal, setDate, setMeal } = useDateMealSelection('LUNCH', tomorrow);
  const mealType = meal as MealType;
  const { data: enumOptions } = useEnumOptions();
  const { data: user } = useCurrentUser();
  const canWrite = canWriteBusinessData(user);

  const generate = useGenerateMenuPlan();
  const dailyGenerate = useGenerateDailyMenuPlan();
  const dailySync = useSyncDailyMenuPlan();
  const plan = generate.data ?? null;
  const dailyPlan: DailyMenuPlanResponse | null = dailyGenerate.data ?? null;
  // 「已同步」只对**当前这一版**成立：换日期或重新生成之后，计划又变回未同步
  const [syncedId, setSyncedId] = useState<string | null>(null);
  const [syncOutcomes, setSyncOutcomes] = useState<DailySyncOutcome[] | null>(null);
  // 单日 / 批量：同一件事的两个粒度，放一页里用模式切换，导航里不再多一个入口
  const [mode, setMode] = useState<'daily' | 'single' | 'batch'>('daily');
  // 结论（待确认 / 已采纳 / 已否决）是会变的，以详情查询为唯一来源；
  // 菜单内容本身来自生成结果——它不可变，没必要再查一次
  const suggestion = useSuggestionDetail(plan?.suggestion_id ?? null);
  const syncMutation = useSyncMenuPlan();
  const synced = plan !== null && syncedId === plan.suggestion_id;

  const handleGenerate = () => {
    setSyncedId(null);
    generate.mutate({ onDate, mealType });
  };

  const handleGenerateDaily = () => {
    setSyncOutcomes(null);
    dailyGenerate.mutate(onDate);
  };

  const handleSync = () => {
    if (!plan) return;
    syncMutation.mutate(
      { onDate: plan.date, mealType: plan.meal_type, suggestionId: plan.suggestion_id },
      { onSuccess: () => setSyncedId(plan.suggestion_id) },
    );
  };

  const handleSyncDaily = () => {
    if (!dailyPlan) return;
    dailySync.mutate(dailyPlan, { onSuccess: (outcomes) => setSyncOutcomes(outcomes) });
  };

  const daily = mode === 'daily';
  const single = mode === 'single';

  return (
    <PagePanel
      filters={
        <>
          <Segmented<'daily' | 'single' | 'batch'>
            value={mode}
            onChange={(value) => {
              setMode(value);
              setSyncOutcomes(null);
            }}
            options={[
              { value: 'daily', label: '一天三餐' },
              { value: 'single', label: '单日' },
              { value: 'batch', label: '批量排菜单' },
            ]}
          />
          {/* 批量用的是它自己的日期区间 */}
          {mode !== 'batch' ? (
            <DatePicker
              value={dayjs(onDate)}
              allowClear={false}
              onChange={(value) => {
                if (value) {
                  setDate(value.format('YYYY-MM-DD'));
                  setSyncedId(null);
                  setSyncOutcomes(null);
                  dailyGenerate.reset();
                }
              }}
            />
          ) : null}
          {mode !== 'daily' ? (
            <Segmented<MealType>
              value={mealType}
              onChange={(value) => {
                setMeal(value);
                setSyncedId(null);
                setSyncOutcomes(null);
                dailyGenerate.reset();
              }}
              options={(enumOptions?.meal_type ?? []).map((option) => ({
                value: option.value as MealType,
                label: option.label,
              }))}
            />
          ) : null}
        </>
      }
      actions={
        <>
          {canWrite && single ? (
            <Button type="primary" loading={generate.isPending} onClick={handleGenerate}>
              生成明日菜单
            </Button>
          ) : null}
          {canWrite && daily ? (
            <Button type="primary" loading={dailyGenerate.isPending} onClick={handleGenerateDaily}>
              生成三餐
            </Button>
          ) : null}
        </>
      }
      bodyClassName="is-padded"
    >
      {daily ? (
        dailyPlan ? (
          <DailyPlanView
            plan={dailyPlan}
            canWrite={canWrite}
            syncing={dailySync.isPending}
            outcomes={syncOutcomes}
            onSync={handleSyncDaily}
          />
        ) : (
          <div className="zw-plan-empty">
            <div className="zw-plan-empty-copy">
              <span className="zw-kicker">一次生成</span>
              <h3>把明天的三餐和采购一起排好</h3>
              <p>
                {canWrite
                  ? '定好日期和餐次，点右上角「生成三餐」即可。'
                  : '三餐菜单由食堂这边生成；生成后这里的菜品与采购单你都能看到。'}
              </p>
            </div>
            <ol>
              <li>
                <span>01</span>
                <div>
                  <strong>配菜</strong>
                  <p>在油盐糖与蛋白质目标下，挑出早、午、晚三餐。</p>
                </div>
              </li>
              <li>
                <span>02</span>
                <div>
                  <strong>定份数</strong>
                  <p>参考同星期历史与就餐人数，给每道菜一份预测。</p>
                </div>
              </li>
              <li>
                <span>03</span>
                <div>
                  <strong>出采购</strong>
                  <p>按配方折算原料，合并成一张可核对的采购单。</p>
                </div>
              </li>
            </ol>
          </div>
        )
      ) : single ? (
        <>
          <Typography.Paragraph type="secondary">
            一次生成三件事：在营养目标下选出做哪几道菜 → 按同星期历史与节假日日历预测每道菜做多少份
            → 按各菜配方算出要买多少料。份数只有一套，采购量就是用它乘出来的。
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
        </>
      ) : (
        <BatchPlanner mealType={mealType} />
      )}
    </PagePanel>
  );
}

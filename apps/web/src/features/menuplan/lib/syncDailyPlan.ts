import { ApiError } from '@/shared/api/errors';
import { syncMenuPlan } from '../api/menuPlanApi';
import type { DailyMenuPlanResponse, MealType } from '../types';

export interface DailySyncOutcome {
  suggestion_id: string;
  meal_type: MealType;
  meal_type_label: string;
  ok: boolean;
  message: string;
}

/** 保留同一方案已成功的餐次；失败餐次逐一重试，不重复写入成功记录。 */
export async function syncDailyPlan({
  plan,
  previous = [],
}: {
  plan: DailyMenuPlanResponse;
  previous?: DailySyncOutcome[];
}): Promise<DailySyncOutcome[]> {
  const outcomes: DailySyncOutcome[] = [];
  for (const meal of plan.meals) {
    const success = previous.find(
      (row) =>
        row.ok && row.meal_type === meal.meal_type && row.suggestion_id === meal.suggestion_id,
    );
    if (success) {
      outcomes.push(success);
      continue;
    }
    const identity = {
      suggestion_id: meal.suggestion_id,
      meal_type: meal.meal_type,
      meal_type_label: meal.meal_type_label,
    };
    try {
      const result = await syncMenuPlan(plan.date, meal.meal_type, meal.suggestion_id);
      outcomes.push({ ...identity, ok: true, message: result.message });
    } catch (error) {
      outcomes.push({
        ...identity,
        ok: false,
        message: error instanceof ApiError ? error.message : '同步失败，请稍后重试',
      });
    }
  }
  return outcomes;
}

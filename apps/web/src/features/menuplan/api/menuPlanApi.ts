import { api } from '@/shared/api/client';
import { unwrap } from '@/shared/api/result';
import type { MealType, MenuPlanResponse } from '../types';

/** 生成「明日菜单与采购」：一次调用把推荐、预测、采购三件事都算完。 */
export async function generateMenuPlan(
  onDate: string,
  mealType: MealType,
  dinerCount?: number,
): Promise<MenuPlanResponse> {
  return unwrap(
    await api.POST('/api/v1/menu-plan/generate', {
      params: { query: { on_date: onDate, meal_type: mealType, diner_count: dinerCount } },
    }),
  );
}

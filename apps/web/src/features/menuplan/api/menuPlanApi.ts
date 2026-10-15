import { api } from '@/shared/api/client';
import { unwrap } from '@/shared/api/result';
import type { MealType, MenuPlanResponse, MenuPlanSyncResult } from '../types';

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

/**
 * 把这一版菜单同步至当日数据。
 *
 * 服务端做三件事：写那一天的菜单日、算好每道菜的单份营养、把这一版记为「已采纳」。
 * 做完之后每日采集的供应菜品就是勾好的，公开大屏当天早上也有内容。
 */
export async function syncMenuPlan(
  onDate: string,
  mealType: MealType,
  suggestionId: string,
): Promise<MenuPlanSyncResult> {
  return unwrap(
    await api.POST('/api/v1/menu-plan/sync', {
      params: {
        query: { on_date: onDate, meal_type: mealType, suggestion_id: suggestionId },
      },
    }),
  );
}

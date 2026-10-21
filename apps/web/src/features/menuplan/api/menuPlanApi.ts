import { api } from '@/shared/api/client';
import { unwrap } from '@/shared/api/result';
import type {
  DailyMenuPlanResponse,
  MealType,
  MenuPlanBatchResult,
  MenuPlanResponse,
  MenuPlanSyncResult,
} from '../types';

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

/** 一键生成早、午、晚三餐，并返回三餐合并后的采购单。 */
export async function generateDailyMenuPlan(onDate: string): Promise<DailyMenuPlanResponse> {
  return unwrap(
    await api.POST('/api/v1/menu-plan/generate-day', {
      params: { query: { on_date: onDate } },
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

/** 按日期区间批量排菜单：一次排一段，逐日生成。 */
export async function generateMenuPlanBatch(
  startDate: string,
  endDate: string,
  mealType: MealType,
): Promise<MenuPlanBatchResult> {
  return unwrap(
    await api.POST('/api/v1/menu-plan/batch/generate', {
      params: {
        query: { start_date: startDate, end_date: endDate, meal_type: mealType },
      },
    }),
  );
}

/** 批量采纳：把区间内每一天最近生成的那一版菜单写进当天的当日数据。 */
export async function syncMenuPlanBatch(
  startDate: string,
  endDate: string,
  mealType: MealType,
  suggestionIds: Record<string, string>,
): Promise<MenuPlanBatchResult> {
  return unwrap(
    await api.POST('/api/v1/menu-plan/batch/sync', {
      body: { suggestion_ids: suggestionIds },
      params: {
        query: { start_date: startDate, end_date: endDate, meal_type: mealType },
      },
    }),
  );
}

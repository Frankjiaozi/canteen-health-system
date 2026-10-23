import type { components } from '@canteen/api-client';

/**
 * 合并页用到的类型。
 *
 * 这里只声明「合并页自己的」响应；采购项、营养差距、推荐理由这些东西各自属于
 * forecast / recommendation 域，直接用它们已导出的类型，免得同一种结构有两个定义。
 */
export type MenuPlanResponse = components['schemas']['MenuPlanResponse'];
export type PlanReadiness = components['schemas']['PlanReadiness'];
export type DailyMenuPlanResponse = components['schemas']['DailyMenuPlanResponse'];
export type MenuPlanDish = components['schemas']['MenuPlanDish'];
export type MenuPlanSyncResult = components['schemas']['MenuPlanSyncResult'];
export type MenuPlanBatchResult = components['schemas']['MenuPlanBatchResult'];
export type MenuPlanBatchDay = components['schemas']['MenuPlanBatchDay'];

export type { IngredientRequirement, MealType } from '@/features/forecast/types';
export type {
  MenuSuggestionRead,
  NutrientGap,
  SuggestionReason,
  SuggestionSummary,
} from '@/features/recommendation/types';

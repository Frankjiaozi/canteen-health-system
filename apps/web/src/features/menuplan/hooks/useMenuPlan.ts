import { useMutation, useQueryClient } from '@tanstack/react-query';
import { App } from 'antd';
import { forecastKeys } from '@/features/forecast/hooks/useForecast';
import { recommendationKeys } from '@/features/recommendation/hooks/useRecommendation';
import { ApiError } from '@/shared/api/errors';
import { generateMenuPlan, syncMenuPlan } from '../api/menuPlanApi';
import type { MealType } from '../types';

/**
 * 生成明天的菜单与采购建议。
 *
 * 结果直接用变更的返回值，不塞进查询缓存：这是「按下去算一次」的动作，
 * 同一天再点应当给出新的一版（菜品轮换与「不连续两日重复」都会让它变），
 * 缓存住反而会让人以为按钮没反应。
 */
export function useGenerateMenuPlan() {
  const queryClient = useQueryClient();
  const { message } = App.useApp();

  return useMutation({
    mutationFn: (input: { onDate: string; mealType: MealType }) =>
      generateMenuPlan(input.onDate, input.mealType),
    onSuccess: async (result) => {
      // 生成会写推荐记录与份数记录，历史列表与回测都要跟着刷新
      await queryClient.invalidateQueries({ queryKey: recommendationKeys.all });
      await queryClient.invalidateQueries({ queryKey: forecastKeys.all });
      void message.success(
        `已排出 ${result.dishes.length} 道菜，采购 ${result.requirements.length} 项`,
      );
    },
    onError: (error: unknown) => {
      // 求解无解时后端会把卡住的约束说清楚，原样展示比「生成失败」有用得多
      void message.error(error instanceof ApiError ? error.message : '生成失败，请稍后重试', 8);
    },
  });
}

/**
 * 同步至当日数据。
 *
 * 这一步会写菜单日、算营养结果，所以采集页、公开大屏、看板都要重新取数——
 * 尤其是采集页：不刷新的话，用户切过去看到的还是「还没有确认菜单」的旧数据。
 */
export function useSyncMenuPlan() {
  const queryClient = useQueryClient();
  const { message } = App.useApp();

  return useMutation({
    mutationFn: (input: { onDate: string; mealType: MealType; suggestionId: string }) =>
      syncMenuPlan(input.onDate, input.mealType, input.suggestionId),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: recommendationKeys.all });
      await queryClient.invalidateQueries({ queryKey: forecastKeys.all });
      await queryClient.invalidateQueries({ queryKey: ['collection'] });
      await queryClient.invalidateQueries({ queryKey: ['public'] });
      void message.success(result.message, 6);
    },
    onError: (error: unknown) => {
      // 「这一天已经录过采集了」这类原因要说给用户看，它决定接下来该去哪儿改
      void message.error(error instanceof ApiError ? error.message : '同步失败，请稍后重试', 8);
    },
  });
}

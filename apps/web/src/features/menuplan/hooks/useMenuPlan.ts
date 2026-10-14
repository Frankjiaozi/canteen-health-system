import { useMutation, useQueryClient } from '@tanstack/react-query';
import { App } from 'antd';
import { forecastKeys } from '@/features/forecast/hooks/useForecast';
import { recommendationKeys } from '@/features/recommendation/hooks/useRecommendation';
import { ApiError } from '@/shared/api/errors';
import { generateMenuPlan } from '../api/menuPlanApi';
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

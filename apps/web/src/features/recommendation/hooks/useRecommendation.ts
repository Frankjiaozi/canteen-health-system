import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App } from 'antd';
import { ApiError } from '@/shared/api/errors';
import {
  decideSuggestion,
  fetchSuggestionById,
  fetchSuggestions,
  generateSuggestion,
} from '../api/recommendationApi';
import type { MealType, SuggestionStatus } from '../types';

export const recommendationKeys = {
  all: ['recommendation'] as const,
  history: (onDate: string) => ['recommendation', 'history', onDate] as const,
  detail: (id: string) => ['recommendation', 'detail', id] as const,
};

export function useSuggestionHistory(onDate: string) {
  return useQuery({
    queryKey: recommendationKeys.history(onDate),
    queryFn: () => fetchSuggestions(onDate),
  });
}

export function useSuggestionDetail(id: string | null) {
  return useQuery({
    queryKey: recommendationKeys.detail(id ?? ''),
    queryFn: () => fetchSuggestionById(id as string),
    enabled: id !== null,
  });
}

/**
 * 生成推荐。
 *
 * 结果直接用变更的返回值，不塞进查询缓存：生成是「按下去算一次」的动作，
 * 同一日期再点应当给出新的一版，缓存住反而会让人以为按钮没反应。
 */
export function useGenerateSuggestion() {
  const queryClient = useQueryClient();
  const { message } = App.useApp();

  return useMutation({
    mutationFn: (input: { onDate: string; mealType: MealType }) =>
      generateSuggestion(input.onDate, input.mealType),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: recommendationKeys.all });
      void message.success(`已生成 ${result.dishes.length} 道菜的菜单建议`);
    },
    onError: (error: unknown) => {
      // 求解器无解时后端会把卡住的约束说清楚，原样展示比「生成失败」有用得多
      void message.error(error instanceof ApiError ? error.message : '生成失败，请稍后重试', 8);
    },
  });
}

export function useDecideSuggestion() {
  const queryClient = useQueryClient();
  const { message } = App.useApp();

  return useMutation({
    mutationFn: (input: { id: string; status: SuggestionStatus; reason: string | null }) =>
      decideSuggestion(input.id, input.status, input.reason),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: recommendationKeys.all });
      void message.success(result.status === 'ACCEPTED' ? '已采纳这份建议' : '已否决并记录原因');
    },
    onError: (error: unknown) => {
      void message.error(error instanceof ApiError ? error.message : '操作失败，请稍后重试');
    },
  });
}

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App } from 'antd';
import { ApiError } from '@/shared/api/errors';
import { decideSuggestion, fetchSuggestionById, fetchSuggestions } from '../api/recommendationApi';
import type { SuggestionStatus } from '../types';

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

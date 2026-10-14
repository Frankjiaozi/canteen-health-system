import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App } from 'antd';
import { ApiError } from '@/shared/api/errors';
import { fetchLogs, fetchSheet, saveSheet } from '../api/collectionApi';
import { describeSaved } from '../lib/sheet';
import type { DailyLogWrite, MealType } from '../types';

export const collectionKeys = {
  all: ['collection'] as const,
  sheet: (onDate: string, mealType: MealType) => ['collection', 'sheet', onDate, mealType] as const,
  logs: (page: number, pageSize: number) => ['collection', 'logs', page, pageSize] as const,
};

export function useDailyLogSheet(onDate: string, mealType: MealType) {
  return useQuery({
    queryKey: collectionKeys.sheet(onDate, mealType),
    queryFn: () => fetchSheet(onDate, mealType),
  });
}

export function useDailyLogList(page: number, pageSize: number) {
  return useQuery({
    queryKey: collectionKeys.logs(page, pageSize),
    queryFn: () => fetchLogs({ page, pageSize }),
    placeholderData: (previous) => previous,
  });
}

/**
 * 保存采集单。
 *
 * 保存会连带重算当餐营养，因此大屏、看板、抽样页的数据都变了——
 * 这里把整棵与日期相关的缓存都作废，免得某个页面还挂着改动前的旧值。
 */
export function useSaveSheet(onDate: string) {
  const queryClient = useQueryClient();
  const { message } = App.useApp();

  return useMutation({
    mutationFn: (payload: DailyLogWrite) => saveSheet(onDate, payload),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: collectionKeys.all });
      await queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      await queryClient.invalidateQueries({ queryKey: ['calibration'] });
      void message.success(describeSaved(result));
    },
    onError: (error: unknown) => {
      void message.error(error instanceof ApiError ? error.message : '保存失败，请稍后重试');
    },
  });
}

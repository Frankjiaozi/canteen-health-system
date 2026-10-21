import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App } from 'antd';
import { authKeys } from '@/features/auth/hooks/useAuth';
import type { AuthUser } from '@/features/auth/types';
import { canWriteBusinessData } from '@/features/auth/lib/permissions';
import { ApiError } from '@/shared/api/errors';
import { fetchLogs, fetchSheet, saveSheet } from '../api/collectionApi';
import { describeSaved } from '../lib/sheet';
import { entryId, shouldQueue } from '../lib/offlineQueue';
import { useOfflineQueueStore, waitForOfflineSync } from './useOfflineQueue';
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
 *
 * 断网时不再让这份录入白填：提交进本地队列，恢复联网后自动补交（见 useSyncOfflineQueue）。
 * 但**服务端明确拒绝的（数据本身有问题）不进队列**——那种要当场告诉录入员改，
 * 替他留着只会让这条记录每次同步都被拒。
 */
export function useSaveSheet(onDate: string, mealType: MealType) {
  const queryClient = useQueryClient();
  const { message } = App.useApp();
  const push = useOfflineQueueStore((state) => state.push);

  return useMutation({
    onMutate: () => {
      const user = queryClient.getQueryData<AuthUser | null>(authKeys.me);
      return {
        ownerId: user?.id,
        queued: user
          ? useOfflineQueueStore
              .getState()
              .entries.find((entry) => entry.id === entryId(onDate, mealType, user.id))
          : undefined,
      };
    },
    mutationFn: async (payload: DailyLogWrite) => {
      const user = queryClient.getQueryData<AuthUser | null>(authKeys.me);
      await waitForOfflineSync();
      const current = queryClient.getQueryData<AuthUser | null>(authKeys.me);
      if (!user || !current || user.id !== current.id || !canWriteBusinessData(current)) {
        throw new ApiError(403, {
          code: 'account_changed',
          message: '账号或权限已变化，请重新登录后提交',
          details: null,
        });
      }
      return saveSheet(onDate, payload);
    },
    // 断网时也要真的发出去、真的失败。TanStack Query 默认的 networkMode: 'online'
    // 会把请求**暂停**在内存里，等联网后自动重放——看起来省事，代价是这件事完全不可见：
    // 录入员看不到「有几条没交上去、卡在哪一条」，刷新页面还会把待同步的静默丢掉。
    // 这里改为 always，让失败显式落到本地队列上（持久化、可查看、可放弃）。
    networkMode: 'always',
    onSuccess: async (result, _payload, context) => {
      if (
        context?.queued &&
        useOfflineQueueStore.getState().entries.find((entry) => entry.id === context.queued?.id) ===
          context.queued
      ) {
        useOfflineQueueStore.getState().drop(context.queued.id);
      }
      await queryClient.invalidateQueries({ queryKey: collectionKeys.all });
      await queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      await queryClient.invalidateQueries({ queryKey: ['calibration'] });
      await queryClient.invalidateQueries({ queryKey: ['public'] });
      void message.success(describeSaved(result));
    },
    onError: (error: unknown, payload: DailyLogWrite, context) => {
      const status = error instanceof ApiError ? error.status : 0;
      if (shouldQueue(status) && context?.ownerId) {
        const { replaced } = push({ ownerId: context.ownerId, onDate, mealType, payload });
        void message.warning(
          replaced
            ? '网络不通，已存入本地队列并覆盖了这一餐先前的待同步记录；联网后会自动补交'
            : '网络不通，已存入本地队列；联网后会自动补交',
          6,
        );
        return;
      }
      void message.error(error instanceof ApiError ? error.message : '保存失败，请稍后重试');
    },
  });
}

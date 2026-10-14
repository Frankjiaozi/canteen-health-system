import { useEffect } from 'react';
import { useQueryClient, type QueryClient } from '@tanstack/react-query';
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { ApiError } from '@/shared/api/errors';
import { useOnlineStatus } from '@/shared/hooks/useOnlineStatus';
import { saveSheet } from '../api/collectionApi';
import {
  enqueue,
  markFailed,
  remove,
  type EnqueueResult,
  type QueuedEntry,
} from '../lib/offlineQueue';
import type { DailyLogWrite, MealType } from '../types';

/**
 * 断网时提交不了的采集单。
 *
 * 这是**纯客户端状态**：它既不在服务端，也不该被服务端缓存覆盖，所以放在 store 里
 * 并用 localStorage 持久化——刷新页面、关掉浏览器再打开，待同步的记录都还在。
 */
interface OfflineQueueState {
  entries: QueuedEntry[];
  push: (input: { onDate: string; mealType: MealType; payload: DailyLogWrite }) => EnqueueResult;
  fail: (id: string, error: string) => void;
  drop: (id: string) => void;
}

export const useOfflineQueueStore = create<OfflineQueueState>()(
  persist(
    (set, get) => ({
      entries: [],
      push: (input) => {
        const result = enqueue(get().entries, {
          ...input,
          now: new Date().toISOString(),
        });
        set({ entries: result.entries });
        return result;
      },
      fail: (id, error) => set({ entries: markFailed(get().entries, id, error) }),
      drop: (id) => set({ entries: remove(get().entries, id) }),
    }),
    { name: 'canteen.collection.offline-queue', version: 1 },
  ),
);

export interface FlushResult {
  synced: number;
  /** 卡住的那一条；为空表示队列已清空 */
  failed: QueuedEntry | null;
}

/**
 * 把队列逐条提交，成功一条删一条。
 *
 * 逐条而不是并发：同一餐的两次提交有先后关系，打散顺序只会让服务端看到更混乱的状态；
 * 而且失败时要把「是哪一条没成功」说清楚，并发之后就说不清了。
 *
 * 一条失败就停：多半是网络又断了或服务端有问题，继续打只会把每条都标红。
 */
export async function flushOfflineQueue(queryClient: QueryClient): Promise<FlushResult> {
  let synced = 0;
  for (const entry of useOfflineQueueStore.getState().entries) {
    try {
      await saveSheet(entry.onDate, entry.payload);
    } catch (error) {
      const message = error instanceof ApiError ? error.message : '同步失败，请稍后重试';
      useOfflineQueueStore.getState().fail(entry.id, message);
      return { synced, failed: { ...entry, lastError: message } };
    }
    useOfflineQueueStore.getState().drop(entry.id);
    synced += 1;
  }
  if (synced > 0) {
    await queryClient.invalidateQueries({ queryKey: ['collection'] });
    await queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    await queryClient.invalidateQueries({ queryKey: ['calibration'] });
  }
  return { synced, failed: null };
}

/**
 * 自动补交。挂在 AdminLayout 上，所以录入员停在任何管理页都会补交，不必回到采集页等。
 */
export function useSyncOfflineQueue(): void {
  const isOnline = useOnlineStatus();
  const entries = useOfflineQueueStore((state) => state.entries);
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!isOnline || entries.length === 0) return;
    void flushOfflineQueue(queryClient);
  }, [isOnline, entries, queryClient]);
}

/** 待同步条数，供界面提示用。 */
export function usePendingCount(): number {
  return useOfflineQueueStore((state) => state.entries.length);
}

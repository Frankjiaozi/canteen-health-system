import { QueryClient } from '@tanstack/react-query';
import { beforeEach, expect, it, vi } from 'vitest';
import { authKeys } from '@/features/auth/hooks/useAuth';
import type { AuthUser } from '@/features/auth/types';
import { saveSheet } from '../api/collectionApi';
import { enqueue } from '../lib/offlineQueue';
import type { DailyLogSaved, DailyLogWrite } from '../types';
import { flushOfflineQueue, useOfflineQueueStore } from './useOfflineQueue';

vi.mock('../api/collectionApi', () => ({ saveSheet: vi.fn() }));
const user: AuthUser = {
  id: 'alice',
  username: 'alice',
  display_name: '甲',
  role: 'RECORDER',
  role_label: '食堂录入员',
};
const payload: DailyLogWrite = {
  meal_type: 'LUNCH',
  diner_count: 100,
  oil_total_g: '50',
  salt_total_g: '20',
  sugar_total_g: '0',
  leftover_weight_g: null,
  dishes: [],
  anomaly_flags: [],
  note: null,
};
const saved = {} as DailyLogSaved;
let client: QueryClient;
const push = (ownerId = 'alice', onDate = '2026-10-20') =>
  useOfflineQueueStore.getState().push({ ownerId, onDate, mealType: 'LUNCH', payload });

beforeEach(() => {
  vi.resetAllMocks();
  useOfflineQueueStore.setState({ entries: [] });
  client = new QueryClient();
  client.setQueryData(authKeys.me, user);
  vi.mocked(saveSheet).mockResolvedValue(saved);
});

it('同一日期不同账号独立排队，只提交当前账号；无归属旧数据不提交', async () => {
  push('alice');
  push('bob');
  const legacy = enqueue(useOfflineQueueStore.getState().entries, {
    onDate: '2026-10-20',
    mealType: 'LUNCH',
    payload,
    now: '2026-10-20T00:00:00Z',
  });
  useOfflineQueueStore.setState({ entries: legacy.entries });
  expect(useOfflineQueueStore.getState().entries).toHaveLength(3);
  await flushOfflineQueue(client);
  expect(saveSheet).toHaveBeenCalledTimes(1);
  expect(useOfflineQueueStore.getState().entries.map((entry) => entry.ownerId)).toEqual([
    undefined,
    'bob',
  ]);
});

it('只读账号即使主动调用补交也不会发出写请求', async () => {
  push();
  client.setQueryData(authKeys.me, { ...user, role: 'SCHOOL_ADMIN' });
  expect((await flushOfflineQueue(client)).paused).toBe(true);
  expect(saveSheet).not.toHaveBeenCalled();
});

it('自动同步和手动补交同时触发时只提交一次', async () => {
  push();
  let release!: (value: DailyLogSaved) => void;
  vi.mocked(saveSheet).mockReturnValue(
    new Promise((resolve) => {
      release = resolve;
    }),
  );
  const automatic = flushOfflineQueue(client, { automatic: true });
  const manual = flushOfflineQueue(client);
  expect(saveSheet).toHaveBeenCalledTimes(1);
  release(saved);
  await Promise.all([automatic, manual]);
  expect(useOfflineQueueStore.getState().entries).toHaveLength(0);
});

it('同步期间重新编辑的同餐草稿不会被旧请求完成后删掉', async () => {
  push();
  let release!: (value: DailyLogSaved) => void;
  vi.mocked(saveSheet).mockReturnValue(
    new Promise((resolve) => {
      release = resolve;
    }),
  );
  const syncing = flushOfflineQueue(client);
  useOfflineQueueStore.getState().push({
    ownerId: 'alice',
    onDate: '2026-10-20',
    mealType: 'LUNCH',
    payload: { ...payload, diner_count: 200 },
  });
  release(saved);
  await syncing;
  expect(useOfflineQueueStore.getState().entries[0].payload.diner_count).toBe(200);
});

it('失败条目不会因队列更新不断自动重试，但仍可手动重试', async () => {
  push();
  vi.mocked(saveSheet).mockRejectedValue(new Error('offline'));
  await flushOfflineQueue(client, { automatic: true });
  await flushOfflineQueue(client, { automatic: true });
  expect(saveSheet).toHaveBeenCalledTimes(1);
  expect(useOfflineQueueStore.getState().entries[0].attempts).toBe(1);
  vi.mocked(saveSheet).mockResolvedValue(saved);
  await flushOfflineQueue(client);
  expect(saveSheet).toHaveBeenCalledTimes(2);
});

it('补交期间切换账号会暂停余下记录，不用新账号继续提交', async () => {
  push('alice', '2026-10-19');
  push('alice', '2026-10-20');
  vi.mocked(saveSheet).mockImplementationOnce(async () => {
    client.setQueryData(authKeys.me, { ...user, id: 'bob' });
    return saved;
  });
  const result = await flushOfflineQueue(client);
  expect(result.paused).toBe(true);
  expect(saveSheet).toHaveBeenCalledTimes(1);
  expect(useOfflineQueueStore.getState().entries).toHaveLength(1);
});

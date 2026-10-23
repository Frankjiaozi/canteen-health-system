import { beforeEach, expect, it, vi } from 'vitest';
import { syncMenuPlan } from '../api/menuPlanApi';
import type { DailyMenuPlanResponse } from '../types';
import { syncDailyPlan } from './syncDailyPlan';

vi.mock('../api/menuPlanApi', () => ({ syncMenuPlan: vi.fn() }));
const plan = {
  date: '2026-10-23',
  meals: [
    { meal_type: 'BREAKFAST', meal_type_label: '早餐', suggestion_id: 'breakfast-1' },
    { meal_type: 'LUNCH', meal_type_label: '午餐', suggestion_id: 'lunch-1' },
    { meal_type: 'DINNER', meal_type_label: '晚餐', suggestion_id: 'dinner-1' },
  ],
} as DailyMenuPlanResponse;

beforeEach(() => {
  vi.mocked(syncMenuPlan).mockReset();
});

it('部分失败后只重试失败餐次，保留成功结果', async () => {
  vi.mocked(syncMenuPlan)
    .mockResolvedValue({ message: '已同步' } as Awaited<ReturnType<typeof syncMenuPlan>>)
    .mockRejectedValueOnce(new Error('offline'));
  const first = await syncDailyPlan({ plan });
  expect(first.map((row) => row.ok)).toEqual([false, true, true]);
  vi.mocked(syncMenuPlan).mockClear();
  const retried = await syncDailyPlan({ plan, previous: first });
  expect(syncMenuPlan).toHaveBeenCalledExactlyOnceWith('2026-10-23', 'BREAKFAST', 'breakfast-1');
  expect(retried.every((row) => row.ok)).toBe(true);
  vi.mocked(syncMenuPlan).mockClear();
  await syncDailyPlan({ plan, previous: retried });
  expect(syncMenuPlan).not.toHaveBeenCalled();
});

it('新方案不能复用旧方案的同步成功状态', async () => {
  vi.mocked(syncMenuPlan).mockResolvedValue({ message: '已同步' } as Awaited<
    ReturnType<typeof syncMenuPlan>
  >);
  const previous = await syncDailyPlan({ plan });
  vi.mocked(syncMenuPlan).mockClear();
  const changed = {
    ...plan,
    meals: plan.meals.map((meal) => ({ ...meal, suggestion_id: meal.suggestion_id + '-new' })),
  };
  await syncDailyPlan({ plan: changed, previous });
  expect(syncMenuPlan).toHaveBeenCalledTimes(3);
});

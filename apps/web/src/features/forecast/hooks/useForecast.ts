import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App } from 'antd';
import { ApiError } from '@/shared/api/errors';
import { fetchBacktest, fetchHolidays, runForecast, updateHoliday } from '../api/forecastApi';
import type { HolidayWrite, MealType } from '../types';

export const forecastKeys = {
  all: ['forecast'] as const,
  backtest: (days: number, mealType: MealType) => ['forecast', 'backtest', days, mealType] as const,
  holidays: (year: number) => ['forecast', 'holidays', year] as const,
};

export function useBacktest(days: number, mealType: MealType) {
  return useQuery({
    queryKey: forecastKeys.backtest(days, mealType),
    queryFn: () => fetchBacktest(days, mealType),
  });
}

export function useHolidays(year: number) {
  return useQuery({
    queryKey: forecastKeys.holidays(year),
    queryFn: () => fetchHolidays(year),
  });
}

/**
 * 生成预测。
 *
 * 结果不放进查询缓存，而是直接用变更的返回值：预测是「按下去算一次」的动作，
 * 同一日期反复算应当给出新结果，塞进缓存反而会出现「点了没反应」的错觉。
 */
export function useRunForecast() {
  const queryClient = useQueryClient();
  const { message } = App.useApp();

  return useMutation({
    mutationFn: (input: { onDate: string; mealType: MealType }) =>
      runForecast(input.onDate, input.mealType),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: forecastKeys.all });
      void message.success(`已生成 ${result.dishes.length} 道菜的份数预测`);
    },
    onError: (error: unknown) => {
      void message.error(error instanceof ApiError ? error.message : '生成失败，请稍后重试');
    },
  });
}

export function useVerifyHoliday(year: number) {
  const queryClient = useQueryClient();
  const { message } = App.useApp();

  return useMutation({
    mutationFn: (input: { id: string; payload: HolidayWrite }) =>
      updateHoliday(input.id, input.payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: forecastKeys.holidays(year) });
      void message.success('日历条目已更新');
    },
    onError: (error: unknown) => {
      void message.error(error instanceof ApiError ? error.message : '更新失败，请稍后重试');
    },
  });
}

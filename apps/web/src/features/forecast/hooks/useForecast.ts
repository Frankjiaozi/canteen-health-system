import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App } from 'antd';
import { ApiError } from '@/shared/api/errors';
import { fetchBacktest, fetchHolidays, updateHoliday } from '../api/forecastApi';
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

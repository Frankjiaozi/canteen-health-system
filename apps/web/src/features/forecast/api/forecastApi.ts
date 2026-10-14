import { api } from '@/shared/api/client';
import { unwrap } from '@/shared/api/result';
import type {
  BacktestResult,
  ForecastRunResult,
  HolidayPage,
  HolidayRead,
  HolidayWrite,
  MealType,
} from '../types';

export async function runForecast(onDate: string, mealType: MealType): Promise<ForecastRunResult> {
  return unwrap(
    await api.POST('/api/v1/forecast/run', {
      params: { query: { on_date: onDate, meal_type: mealType } },
    }),
  );
}

export async function fetchBacktest(days: number, mealType: MealType): Promise<BacktestResult> {
  return unwrap(
    await api.GET('/api/v1/forecast/backtest', {
      params: { query: { days, meal_type: mealType } },
    }),
  );
}

export async function fetchHolidays(year: number): Promise<HolidayPage> {
  return unwrap(await api.GET('/api/v1/forecast/holidays', { params: { query: { year } } }));
}

export async function updateHoliday(id: string, payload: HolidayWrite): Promise<HolidayRead> {
  return unwrap(
    await api.PATCH('/api/v1/forecast/holidays/{holiday_id}', {
      params: { path: { holiday_id: id } },
      body: payload,
    }),
  );
}

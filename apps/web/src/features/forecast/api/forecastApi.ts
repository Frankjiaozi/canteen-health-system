import { api } from '@/shared/api/client';
import { unwrap } from '@/shared/api/result';
import type { BacktestResult, HolidayPage, HolidayRead, HolidayWrite, MealType } from '../types';

/**
 * 回测与日历。生成份数这件事不在这个域的前端里做——它由「明日菜单与采购」一次调用完成
 * （见 features/menuplan），份数的依据与回测结果在这两个接口里查。
 */
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

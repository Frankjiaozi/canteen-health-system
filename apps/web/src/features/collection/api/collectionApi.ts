import { api } from '@/shared/api/client';
import { unwrap } from '@/shared/api/result';
import type { DailyLogPage, DailyLogSaved, DailyLogSheet, DailyLogWrite, MealType } from '../types';

export async function fetchSheet(onDate: string, mealType: MealType): Promise<DailyLogSheet> {
  return unwrap(
    await api.GET('/api/v1/collection/logs/{on_date}', {
      params: { path: { on_date: onDate }, query: { meal_type: mealType } },
    }),
  );
}

export async function saveSheet(onDate: string, payload: DailyLogWrite): Promise<DailyLogSaved> {
  return unwrap(
    await api.PUT('/api/v1/collection/logs/{on_date}', {
      params: { path: { on_date: onDate } },
      body: payload,
    }),
  );
}

export async function fetchLogs(params: {
  page: number;
  pageSize: number;
  start?: string;
  end?: string;
}): Promise<DailyLogPage> {
  return unwrap(
    await api.GET('/api/v1/collection/logs', {
      params: {
        query: {
          page: params.page,
          page_size: params.pageSize,
          start: params.start,
          end: params.end,
        },
      },
    }),
  );
}

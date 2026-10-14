import { api } from '@/shared/api/client';
import { unwrap } from '@/shared/api/result';
import type {
  ClosureRunResponse,
  MealType,
  SampleCreate,
  SampleResult,
  SamplingCandidates,
} from '../types';

export async function fetchCandidates(
  onDate: string,
  mealType: MealType,
): Promise<SamplingCandidates> {
  return unwrap(
    await api.GET('/api/v1/calibration/candidates', {
      params: { query: { on_date: onDate, meal_type: mealType } },
    }),
  );
}

export async function submitSample(payload: SampleCreate): Promise<SampleResult> {
  return unwrap(await api.POST('/api/v1/calibration/samples', { body: payload }));
}

export async function runDailyClosure(
  onDate: string,
  mealType: MealType,
): Promise<ClosureRunResponse> {
  return unwrap(
    await api.POST('/api/v1/calibration/daily-closure', {
      params: { query: { on_date: onDate, meal_type: mealType } },
    }),
  );
}

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App } from 'antd';
import { ApiError } from '@/shared/api/errors';
import { collectionKeys } from '@/features/collection/hooks/useCollection';
import { fetchCandidates, runDailyClosure, submitSample } from '../api/calibrationApi';
import { describeSampleResult } from '../lib/compare';
import type { MealType, SampleCreate } from '../types';

export const calibrationKeys = {
  all: ['calibration'] as const,
  candidates: (onDate: string, mealType: MealType) =>
    ['calibration', 'candidates', onDate, mealType] as const,
};

export function useSamplingCandidates(onDate: string, mealType: MealType) {
  return useQuery({
    queryKey: calibrationKeys.candidates(onDate, mealType),
    queryFn: () => fetchCandidates(onDate, mealType),
  });
}

/**
 * 校准会改写当餐的营养结果与当天记录上的异常标记，所以缓存要一并作废：
 * 大屏、看板与采集单读的都是同一份数据，漏掉任何一处都会留下前后不一致的画面。
 */
function useCalibrationInvalidate() {
  const queryClient = useQueryClient();
  return async () => {
    await queryClient.invalidateQueries({ queryKey: calibrationKeys.all });
    await queryClient.invalidateQueries({ queryKey: collectionKeys.all });
    await queryClient.invalidateQueries({ queryKey: ['dashboard'] });
  };
}

export function useSubmitSample() {
  const invalidate = useCalibrationInvalidate();
  const { message } = App.useApp();

  return useMutation({
    mutationFn: (payload: SampleCreate) => submitSample(payload),
    onSuccess: async (result) => {
      await invalidate();
      // 疑似配方有误时用警告色，避免录入员以为一切正常
      if (result.suspect_recipe) {
        void message.warning(describeSampleResult(result), 6);
      } else {
        void message.success(describeSampleResult(result));
      }
    },
    onError: (error: unknown) => {
      void message.error(error instanceof ApiError ? error.message : '提交失败，请稍后重试');
    },
  });
}

export function useRunDailyClosure(onDate: string) {
  const invalidate = useCalibrationInvalidate();
  const { message } = App.useApp();

  return useMutation({
    mutationFn: (mealType: MealType) => runDailyClosure(onDate, mealType),
    onSuccess: async (result) => {
      await invalidate();
      void message.success(
        `${result.meal_type_label}校准完成：${result.factors.length} 类烹饪方式，重算 ${result.calibrated_rows} 条`,
      );
    },
    onError: (error: unknown) => {
      void message.error(error instanceof ApiError ? error.message : '校准失败，请稍后重试');
    },
  });
}

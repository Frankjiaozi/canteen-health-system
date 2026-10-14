import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App } from 'antd';
import { ApiError } from '@/shared/api/errors';
import {
  createDish,
  deactivateDish,
  fetchDish,
  fetchDishes,
  importDishes,
  saveRecipe,
  updateDish,
  type DishListParams,
} from '../api/dishApi';
import {
  createSeasoning,
  deactivateSeasoning,
  fetchSeasonings,
  updateSeasoning,
  type SeasoningListParams,
} from '../api/seasoningApi';
import type {
  DishCreatePayload,
  DishUpdatePayload,
  RecipePayload,
  SeasoningCreatePayload,
  SeasoningUpdatePayload,
} from '../types';

export const dishKeys = {
  all: ['dishes'] as const,
  list: (params: DishListParams) => ['dishes', 'list', params] as const,
  detail: (id: string) => ['dishes', 'detail', id] as const,
};

export const seasoningKeys = {
  all: ['seasonings'] as const,
  list: (params: SeasoningListParams) => ['seasonings', 'list', params] as const,
};

export function useDishList(params: DishListParams) {
  return useQuery({
    queryKey: dishKeys.list(params),
    queryFn: () => fetchDishes(params),
    placeholderData: (previous) => previous,
  });
}

export function useDishDetail(id: string | null) {
  return useQuery({
    queryKey: dishKeys.detail(id ?? ''),
    queryFn: () => fetchDish(id as string),
    enabled: id !== null,
  });
}

export function useSeasoningList(params: SeasoningListParams) {
  return useQuery({
    queryKey: seasoningKeys.list(params),
    queryFn: () => fetchSeasonings(params),
    placeholderData: (previous) => previous,
  });
}

/** 写操作统一处理成功提示与失败提示。后端返回的 message 已是面向用户的中文文案。 */
function useWriteMutation<TArgs, TResult>(
  mutationFn: (args: TArgs) => Promise<TResult>,
  successText: string,
  keys: readonly (readonly unknown[])[],
) {
  const queryClient = useQueryClient();
  const { message } = App.useApp();

  return useMutation({
    mutationFn,
    onSuccess: async () => {
      await Promise.all(keys.map((key) => queryClient.invalidateQueries({ queryKey: key })));
      void message.success(successText);
    },
    onError: (error: unknown) => {
      void message.error(error instanceof ApiError ? error.message : '操作失败，请稍后重试');
    },
  });
}

export function useCreateDish() {
  return useWriteMutation((payload: DishCreatePayload) => createDish(payload), '菜品已新增', [
    dishKeys.all,
  ]);
}

export function useUpdateDish() {
  return useWriteMutation(
    (args: { id: string; payload: DishUpdatePayload }) => updateDish(args.id, args.payload),
    '菜品已更新',
    [dishKeys.all],
  );
}

export function useDeactivateDish() {
  return useWriteMutation((id: string) => deactivateDish(id), '菜品已停用', [dishKeys.all]);
}

export function useSaveRecipe() {
  return useWriteMutation(
    (args: { id: string; payload: RecipePayload }) => saveRecipe(args.id, args.payload),
    '配方已保存，营养结果已重算',
    [dishKeys.all, ['public'], ['dashboard']],
  );
}

export function useCreateSeasoning() {
  return useWriteMutation(
    (payload: SeasoningCreatePayload) => createSeasoning(payload),
    '调味料已新增',
    [seasoningKeys.all],
  );
}

export function useUpdateSeasoning() {
  return useWriteMutation(
    (args: { id: string; payload: SeasoningUpdatePayload }) =>
      updateSeasoning(args.id, args.payload),
    '调味料已更新',
    [seasoningKeys.all],
  );
}

export function useDeactivateSeasoning() {
  return useWriteMutation((id: string) => deactivateSeasoning(id), '调味料已停用', [
    seasoningKeys.all,
  ]);
}

export function useImportDishes() {
  // 导入分「校验」与「执行」两步，提示文案与刷新时机都由界面自己掌握，
  // 因此这里不用带自动提示的通用包装
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (args: { file: File; dryRun: boolean }) => importDishes(args.file, args.dryRun),
    onSuccess: async (_report, variables) => {
      if (variables.dryRun) return;
      await Promise.all(
        [dishKeys.all, seasoningKeys.all, ['ingredients']].map((key) =>
          queryClient.invalidateQueries({ queryKey: key }),
        ),
      );
    },
  });
}

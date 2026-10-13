import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App } from 'antd';
import { ApiError } from '@/shared/api/errors';
import {
  createIngredient,
  deactivateIngredient,
  fetchIngredients,
  updateIngredient,
} from '../api/ingredientApi';
import type { IngredientQueryParams } from '../lib/query';
import type { IngredientCreatePayload, IngredientUpdatePayload } from '../types';

export const ingredientKeys = {
  all: ['ingredients'] as const,
  list: (params: IngredientQueryParams) => ['ingredients', 'list', params] as const,
};

export function useIngredientList(params: IngredientQueryParams) {
  return useQuery({
    queryKey: ingredientKeys.list(params),
    queryFn: () => fetchIngredients(params),
    // 翻页时保留上一页内容，避免表格闪成空白
    placeholderData: (previous) => previous,
  });
}

/**
 * 写操作统一在这里处理成功提示与失败提示。
 *
 * 后端返回的 message 已经是面向用户的中文文案（例如「食材「西兰花」已存在」），
 * 直接展示即可；非 ApiError 的异常才用兜底文案。
 */
function useIngredientMutation<TArgs, TResult>(
  mutationFn: (args: TArgs) => Promise<TResult>,
  successText: string,
) {
  const queryClient = useQueryClient();
  const { message } = App.useApp();

  return useMutation({
    mutationFn,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ingredientKeys.all });
      void message.success(successText);
    },
    onError: (error: unknown) => {
      void message.error(error instanceof ApiError ? error.message : '操作失败，请稍后重试');
    },
  });
}

export function useCreateIngredient() {
  return useIngredientMutation(
    (payload: IngredientCreatePayload) => createIngredient(payload),
    '食材已新增',
  );
}

export function useUpdateIngredient() {
  return useIngredientMutation(
    (args: { id: string; payload: IngredientUpdatePayload }) =>
      updateIngredient(args.id, args.payload),
    '食材已更新',
  );
}

export function useDeactivateIngredient() {
  return useIngredientMutation((id: string) => deactivateIngredient(id), '食材已停用');
}

import { api } from '@/shared/api/client';
import { toApiError } from '@/shared/api/errors';
import { unwrap } from '@/shared/api/result';
import type {
  DishCategory,
  DishCreatePayload,
  DishDetail,
  DishPage,
  DishUpdatePayload,
  ImportReport,
  RecipePayload,
  RecipeUpdateResult,
} from '../types';

export interface DishListParams {
  page: number;
  pageSize: number;
  keyword?: string;
  category?: DishCategory | null;
  includeInactive?: boolean;
}

export async function fetchDishes(params: DishListParams): Promise<DishPage> {
  const keyword = params.keyword?.trim();
  return unwrap(
    await api.GET('/api/v1/dishes', {
      params: {
        query: {
          page: params.page,
          page_size: params.pageSize,
          include_inactive: params.includeInactive ?? false,
          ...(keyword ? { keyword } : {}),
          ...(params.category ? { category: params.category } : {}),
        },
      },
    }),
  );
}

export async function fetchDish(id: string): Promise<DishDetail> {
  return unwrap(await api.GET('/api/v1/dishes/{dish_id}', { params: { path: { dish_id: id } } }));
}

export async function createDish(payload: DishCreatePayload): Promise<DishDetail> {
  return unwrap(await api.POST('/api/v1/dishes', { body: payload }));
}

export async function updateDish(id: string, payload: DishUpdatePayload): Promise<DishDetail> {
  return unwrap(
    await api.PATCH('/api/v1/dishes/{dish_id}', {
      params: { path: { dish_id: id } },
      body: payload,
    }),
  );
}

export async function saveRecipe(id: string, payload: RecipePayload): Promise<RecipeUpdateResult> {
  return unwrap(
    await api.PUT('/api/v1/dishes/{dish_id}/recipe', {
      params: { path: { dish_id: id } },
      body: payload,
    }),
  );
}

export async function deactivateDish(id: string): Promise<DishDetail> {
  return unwrap(
    await api.DELETE('/api/v1/dishes/{dish_id}', { params: { path: { dish_id: id } } }),
  );
}

/**
 * 上传 Excel。刻意不走生成的客户端：multipart 的请求体在类型上表达不出来，
 * 与生成的类型较劲不如直接用 fetch——同源、带 Cookie，与别处一模一样。
 */
export async function importDishes(file: File, dryRun: boolean): Promise<ImportReport> {
  const body = new FormData();
  body.append('file', file);

  const response = await fetch(`/api/v1/import/dishes?dry_run=${dryRun}`, {
    method: 'POST',
    body,
    credentials: 'include',
  });
  const payload: unknown = await response.json();
  if (!response.ok) {
    throw toApiError(response.status, payload);
  }
  return payload as ImportReport;
}

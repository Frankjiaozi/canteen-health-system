import { api } from '@/shared/api/client';
import { unwrap } from '@/shared/api/result';
import type {
  Seasoning,
  SeasoningCategory,
  SeasoningCreatePayload,
  SeasoningUpdatePayload,
} from '../types';

export interface SeasoningListParams {
  page: number;
  pageSize: number;
  keyword?: string;
  category?: SeasoningCategory | null;
  includeInactive?: boolean;
}

export async function fetchSeasonings(params: SeasoningListParams) {
  const keyword = params.keyword?.trim();
  return unwrap(
    await api.GET('/api/v1/seasonings', {
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

export async function createSeasoning(payload: SeasoningCreatePayload): Promise<Seasoning> {
  return unwrap(await api.POST('/api/v1/seasonings', { body: payload }));
}

export async function updateSeasoning(
  id: string,
  payload: SeasoningUpdatePayload,
): Promise<Seasoning> {
  return unwrap(
    await api.PATCH('/api/v1/seasonings/{seasoning_id}', {
      params: { path: { seasoning_id: id } },
      body: payload,
    }),
  );
}

export async function deactivateSeasoning(id: string): Promise<Seasoning> {
  return unwrap(
    await api.DELETE('/api/v1/seasonings/{seasoning_id}', {
      params: { path: { seasoning_id: id } },
    }),
  );
}

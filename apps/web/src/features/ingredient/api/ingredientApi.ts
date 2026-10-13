import { api } from '@/shared/api/client';
import { unwrap } from '@/shared/api/result';
import { buildIngredientQuery, type IngredientQueryParams } from '../lib/query';
import type {
  Ingredient,
  IngredientCreatePayload,
  IngredientPage,
  IngredientUpdatePayload,
} from '../types';

export async function fetchIngredients(params: IngredientQueryParams): Promise<IngredientPage> {
  return unwrap(
    await api.GET('/api/v1/ingredients', { params: { query: buildIngredientQuery(params) } }),
  );
}

export async function createIngredient(payload: IngredientCreatePayload): Promise<Ingredient> {
  return unwrap(await api.POST('/api/v1/ingredients', { body: payload }));
}

export async function updateIngredient(
  id: string,
  payload: IngredientUpdatePayload,
): Promise<Ingredient> {
  return unwrap(
    await api.PATCH('/api/v1/ingredients/{ingredient_id}', {
      params: { path: { ingredient_id: id } },
      body: payload,
    }),
  );
}

export async function deactivateIngredient(id: string): Promise<Ingredient> {
  return unwrap(
    await api.DELETE('/api/v1/ingredients/{ingredient_id}', {
      params: { path: { ingredient_id: id } },
    }),
  );
}

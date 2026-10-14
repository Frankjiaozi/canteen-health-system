import type { components } from '@canteen/api-client';

export type Ingredient = components['schemas']['IngredientRead'];
export type IngredientCategory = components['schemas']['IngredientCategory'];
export type IngredientCreatePayload = components['schemas']['IngredientCreate'];
export type IngredientUpdatePayload = components['schemas']['IngredientUpdate'];
export type IngredientPage = components['schemas']['IngredientPage'];

/** 营养成分与可食部比例在接口里以字符串传输（Decimal），小数位见 shared/config/nutrients。 */
export { NUTRIENT_COLUMNS } from '@/shared/config/nutrients';

import type { components } from '@canteen/api-client';

export type Ingredient = components['schemas']['IngredientRead'];
export type IngredientCategory = components['schemas']['IngredientCategory'];
export type IngredientCreatePayload = components['schemas']['IngredientCreate'];
export type IngredientUpdatePayload = components['schemas']['IngredientUpdate'];
export type IngredientPage = components['schemas']['IngredientPage'];

/** 营养成分与可食部比例在接口里以字符串传输（Decimal），这里集中描述小数位。 */
export const NUTRIENT_COLUMNS = [
  { field: 'energy_kcal', title: '能量', unit: '千卡', digits: 2 },
  { field: 'protein_g', title: '蛋白质', unit: '克', digits: 3 },
  { field: 'fat_g', title: '脂肪', unit: '克', digits: 3 },
  { field: 'carb_g', title: '碳水化合物', unit: '克', digits: 3 },
  { field: 'sodium_mg', title: '钠', unit: '毫克', digits: 2 },
] as const satisfies ReadonlyArray<{
  field: keyof Ingredient;
  title: string;
  unit: string;
  digits: number;
}>;

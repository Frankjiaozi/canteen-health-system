// 五项核心营养指标的展示配置。
//
// 食材库、调味料库、菜品页都用同一份——单位与小数位各写一遍，迟早会对不上。
export interface NutrientColumn {
  field: 'energy_kcal' | 'protein_g' | 'fat_g' | 'carb_g' | 'sodium_mg';
  title: string;
  unit: string;
  digits: number;
}

export const NUTRIENT_COLUMNS: readonly NutrientColumn[] = [
  { field: 'energy_kcal', title: '能量', unit: '千卡', digits: 2 },
  { field: 'protein_g', title: '蛋白质', unit: '克', digits: 3 },
  { field: 'fat_g', title: '脂肪', unit: '克', digits: 3 },
  { field: 'carb_g', title: '碳水化合物', unit: '克', digits: 3 },
  { field: 'sodium_mg', title: '钠', unit: '毫克', digits: 2 },
];

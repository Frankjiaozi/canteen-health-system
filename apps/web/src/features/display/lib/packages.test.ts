import { describe, expect, it } from 'vitest';
import type { PublicDishCard } from '../types';
import { availablePackages, dishesForPackage } from './packages';

function dish(name: string, packageCodes?: PublicDishCard['package_codes']): PublicDishCard {
  return {
    dish_id: name,
    name,
    package_codes: packageCodes,
    is_shared: packageCodes?.includes('COMMON') ?? false,
    category_label: '素菜',
    cooking_method_label: '炒',
    standard_serving_g: '100',
    allergens: [],
    nutrients: [],
    recipe_version: 1,
    value_type: 'THEORETICAL',
    value_type_label: '理论值',
    missing_nutrients: [],
  };
}

describe('公开大屏套餐筛选', () => {
  const rows = [dish('米饭', ['COMMON']), dish('西兰花', ['A']), dish('油菜', ['B'])];

  it('只展示当前套餐和共用主食', () => {
    expect(dishesForPackage(rows, 'A').map((row) => row.name)).toEqual(['米饭', '西兰花']);
    expect(dishesForPackage(rows, 'B').map((row) => row.name)).toEqual(['米饭', '油菜']);
  });

  it('旧数据没有套餐标识时保留完整菜单', () => {
    const legacy = [dish('旧菜单')];
    expect(availablePackages(legacy)).toEqual([]);
    expect(dishesForPackage(legacy, null)).toEqual(legacy);
  });
});

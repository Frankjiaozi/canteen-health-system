import { describe, expect, it } from 'vitest';
import type { PlanVersion } from '../api/types';
import { comparePlans, formatAmount } from './compare';

function version(cost: string | null, ids: string[], date = '2026-10-17'): PlanVersion {
  return {
    revision: 1,
    created_at: '2026-10-16T12:00:00+08:00',
    parameters: {
      on_date: date,
      meal_type: 'LUNCH',
      diner_count: 800,
      budget_per_person: '8',
      excluded_dish_ids: [],
    },
    publication: null,
    data_notice: '合成演示数据',
    result: {
      date,
      meal_type: 'LUNCH',
      meal_type_label: '午餐',
      diner_count: 800,
      suggestion_id: 'test-plan',
      dishes: ids.map((id) => ({
        dish_id: id,
        dish_name: id,
        category_label: '素菜',
        cooking_method_label: '蒸',
        energy_kcal: '100',
        salt_g: '1',
        popularity: '20',
        nutrition_basis: '理论值',
        predicted_servings: '200',
        prediction_fallback: false,
      })),
      gaps: [],
      reasons: [],
      requirements: [],
      total_cost: cost,
      budget: '6400',
      target_basis: {},
      excluded_dishes: [],
      calendar_notes: [],
      skipped_predictions: [],
      servings_note: '采购按预测份数计算',
      notes: [],
      snapshot_token: 'a'.repeat(64),
      expected_menu_token: 'b'.repeat(64),
      budget_per_person: '8',
    },
  };
}

describe('方案比较的解释边界', () => {
  it('分别标出新增与移除，不把保留菜品重复计算', () => {
    const result = comparePlans(version('1100', ['a', 'c']), version('1000', ['a', 'b']));
    expect(result.added.map((row) => row.dish_id)).toEqual(['c']);
    expect(result.removed.map((row) => row.dish_id)).toEqual(['b']);
    expect(result.costDelta).toBe(100);
  });
  it('缺少金额不能被当作零元节省', () => {
    expect(comparePlans(version(null, ['a']), version('1000', ['a'])).costDelta).toBeNull();
    expect(formatAmount(null)).toBe('—');
    expect(formatAmount('invalid')).toBe('—');
    expect(formatAmount('0')).toBe('0.00');
  });
  it('日期不同的方案标记为不同范围', () => {
    expect(
      comparePlans(version('100', ['a'], '2026-10-18'), version('1000', ['a'])).sameScope,
    ).toBe(false);
  });
  it('只合计了已知单价的金额不能当作完整差额', () => {
    const partial = version('100', ['a']);
    partial.result.missing_price_warning = '部分原料缺单价';
    expect(comparePlans(partial, version('1000', ['a'])).costDelta).toBeNull();
  });
});

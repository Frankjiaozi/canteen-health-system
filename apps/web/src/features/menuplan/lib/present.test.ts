import { describe, expect, it } from 'vitest';
import type { IngredientRequirement, MenuPlanDish } from '../types';
import { describePredictionOrigin, summarizePurchase } from './present';

function dish(overrides: Partial<MenuPlanDish> = {}): MenuPlanDish {
  return {
    dish_id: 'd1',
    dish_name: '宫保鸡丁',
    category_label: '半荤',
    cooking_method_label: '炒',
    energy_kcal: '210.5',
    salt_g: '2.1',
    popularity: '320',
    nutrition_basis: '理论值',
    predicted_servings: '376.32',
    predicted_basis_label: '同星期几平均',
    prediction_fallback: false,
    ...overrides,
  };
}

function row(name: string, cost: string | null): IngredientRequirement {
  return {
    name,
    unit: '公斤',
    quantity: '10.000',
    unit_price: cost === null ? null : '12.00',
    estimated_cost: cost,
  };
}

describe('describePredictionOrigin', () => {
  it('能预测时给出份数与依据，份数按整数说', () => {
    expect(describePredictionOrigin(dish())).toEqual({
      text: '376 份，同星期几平均',
      tone: 'forecast',
    });
  });

  it('预测不出来时如实说是估的，不冒充预测值', () => {
    const fallback = describePredictionOrigin(
      dish({ predicted_servings: null, prediction_fallback: true }),
    );
    expect(fallback.tone).toBe('fallback');
    expect(fallback.text).toContain('每人一份');
  });

  it('份数为空时也当作估的，避免出现「— 份」这种看不出来源的写法', () => {
    expect(describePredictionOrigin(dish({ predicted_servings: null })).tone).toBe('fallback');
  });
});

describe('summarizePurchase', () => {
  it('在预算内时不报警', () => {
    const summary = summarizePurchase([row('牛肉', '2091.88')], '2091.88', '7080.00');
    expect(summary.tone).toBe('ok');
    expect(summary.note).toBe('');
  });

  it('超预算时说出超了多少', () => {
    const summary = summarizePurchase([row('牛肉', '8000.00')], '8000.00', '7080.00');
    expect(summary.tone).toBe('over');
    expect(summary.note).toBe('超出预算 920.00 元');
  });

  it('缺单价时说清是哪几项、合计因此偏低', () => {
    const summary = summarizePurchase(
      [row('牛肉', '100.00'), row('虾皮', null)],
      '100.00',
      '500.00',
    );
    expect(summary.tone).toBe('incomplete');
    expect(summary.note).toContain('虾皮');
    expect(summary.note).toContain('偏低');
  });

  it('金额缺失时不拿它去比预算', () => {
    const summary = summarizePurchase([row('虾皮', null)], null, '500.00');
    expect(summary.tone).toBe('incomplete');
    expect(summary.text).toContain('—');
  });
});

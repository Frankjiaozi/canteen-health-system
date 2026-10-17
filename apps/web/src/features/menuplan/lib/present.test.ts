import { describe, expect, it } from 'vitest';
import type { IngredientRequirement, MenuPlanBatchDay, MenuPlanDish } from '../types';
import {
  batchStatusTone,
  describePredictionOrigin,
  mergeBatchStatuses,
  summarizePurchase,
} from './present';

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

function batchDay(overrides: Partial<MenuPlanBatchDay> = {}): MenuPlanBatchDay {
  return {
    date: '2026-12-03',
    status: 'GENERATED',
    status_label: '已生成',
    dish_names: ['米饭', '紫菜蛋花汤'],
    dish_count: 2,
    diner_count: 885,
    cost_per_person: '3.20',
    requirements_count: 0,
    nutrition_rows: 0,
    ...overrides,
  };
}

describe('批量结果的状态口径', () => {
  it('生成和导入都算成了，跳过与排不出来各自另说', () => {
    expect(batchStatusTone('GENERATED')).toBe('ok');
    expect(batchStatusTone('IMPORTED')).toBe('ok');
    expect(batchStatusTone('SKIPPED')).toBe('skipped');
    expect(batchStatusTone('FAILED')).toBe('bad');
  });
});

describe('导入结果与生成结果的合并', () => {
  it('状态用导入那一次，菜品与金额沿用生成那一次', () => {
    const merged = mergeBatchStatuses(
      [batchDay()],
      [
        batchDay({
          status: 'IMPORTED',
          status_label: '已导入',
          dish_names: [],
          dish_count: 0,
          cost_per_person: undefined,
          nutrition_rows: 2,
        }),
      ],
    );

    expect(merged[0].status).toBe('IMPORTED');
    expect(merged[0].nutrition_rows).toBe(2);
    expect(merged[0].dish_names).toEqual(['米饭', '紫菜蛋花汤']);
    expect(merged[0].cost_per_person).toBe('3.20');
  });

  it('导入失败时，失败原因要盖住原来的成功状态——否则看着像导进去了', () => {
    const merged = mergeBatchStatuses(
      [batchDay()],
      [
        batchDay({
          status: 'FAILED',
          status_label: '导入失败',
          reason: '这一天已经录过采集了',
        }),
      ],
    );

    expect(merged[0].status).toBe('FAILED');
    expect(merged[0].reason).toBe('这一天已经录过采集了');
  });

  it('导入没提到的日期保持原样', () => {
    const merged = mergeBatchStatuses([batchDay({ date: '2026-12-04' })], []);
    expect(merged[0].date).toBe('2026-12-04');
    expect(merged[0].status).toBe('GENERATED');
  });
});

import { describe, expect, it } from 'vitest';
import type { DailyLogSheet } from '../types';
import {
  buildSavePayload,
  describeSaved,
  formatPlannedServings,
  initialFormValues,
  initialRows,
  toNumber,
  validateSheet,
  type SheetFormValues,
  type SheetRow,
} from './sheet';

const sheet = {
  date: '2026-10-14',
  meal_type: 'LUNCH',
  meal_type_label: '午餐',
  saved: true,
  submitted_at: null,
  diner_count: 885,
  oil_total_g: '6242.84',
  salt_total_g: '2087.46',
  sugar_total_g: '1479.00',
  leftover_weight_g: null,
  note: null,
  anomaly_flags: [
    { value: 'RECEPTION', label: '临时接待', system: false },
    { value: 'CALIBRATION_RESIDUAL', label: '用量对不上（系统判定）', system: true },
  ],
  dishes: [
    {
      dish_id: 'a',
      name: '土豆炖牛肉',
      category_label: '荤菜',
      cooking_method_label: '炖',
      selected: true,
      servings_produced: '451.00',
      leftover_ratio: '0.0500',
      leftover_weight_g: null,
      is_substituted: false,
      substitution_note: null,
      energy_kcal: '193.57',
      nutrition_source: '按历史采集的油盐糖实际用量校准',
    },
    {
      dish_id: 'b',
      name: '清炒西兰花',
      category_label: '素菜',
      cooking_method_label: '炒',
      selected: false,
      servings_produced: null,
      leftover_ratio: null,
      leftover_weight_g: null,
      is_substituted: false,
      substitution_note: null,
      energy_kcal: null,
      nutrition_source: null,
    },
  ],
  menu_confirmed: true,
  warning: null,
} as unknown as DailyLogSheet;

const validValues = (): SheetFormValues => ({
  dinerCount: 885,
  oilTotalG: 6242.84,
  saltTotalG: 2087.46,
  sugarTotalG: 1479,
  leftoverWeightG: null,
  note: null,
  anomalyFlags: ['RECEPTION'],
  mealType: 'LUNCH',
});

const selectedRow = (overrides: Partial<SheetRow> = {}): SheetRow => ({
  dishId: 'a',
  selected: true,
  servings: 451,
  leftoverRatio: 0.05,
  isSubstituted: false,
  substitutionNote: null,
  ...overrides,
});

describe('采集单的初始状态', () => {
  it('修改其他字段后重新保存，不清空已有逐菜剩餐重量', () => {
    const withWeight = {
      ...sheet,
      dishes: sheet.dishes.map((dish) => ({ ...dish, leftover_weight_g: '123.45' })),
    };
    const payload = buildSavePayload(validValues(), initialRows(withWeight));
    expect(payload.dishes?.[0].leftover_weight_g).toBe('123.45');
  });
  it('沿用库里已保存的值，未保存的菜保持未勾选', () => {
    const rows = initialRows(sheet);

    expect(rows[0]).toMatchObject({ dishId: 'a', selected: true, servings: 451 });
    expect(rows[1]).toMatchObject({ dishId: 'b', selected: false, servings: null });
  });

  it('人工标记进入表单，系统回写的标记不进入——它不是让人去勾的', () => {
    const values = initialFormValues(sheet);

    expect(values.anomalyFlags).toEqual(['RECEPTION']);
    expect(values.dinerCount).toBe(885);
  });
});

describe('提交前校验', () => {
  it('一道菜都没勾时给出能照做的提示', () => {
    expect(validateSheet(validValues(), [selectedRow({ selected: false })])).toContain('勾选');
  });

  it('就餐人次缺失时说清为什么要填', () => {
    const values = { ...validValues(), dinerCount: null };

    expect(validateSheet(values, [selectedRow()])).toContain('人均摄入');
  });

  it('勾了的菜没填份数时指出还差几道', () => {
    const rows = [selectedRow(), selectedRow({ dishId: 'b', servings: null })];

    expect(validateSheet(validValues(), rows)).toContain('1 道');
  });

  it('剩余比例超出 0~1 时说明正确写法', () => {
    const rows = [selectedRow({ leftoverRatio: 1.5 })];

    expect(validateSheet(validValues(), rows)).toContain('0.2');
  });

  it('都填对时放行', () => {
    expect(validateSheet(validValues(), [selectedRow()])).toBeNull();
  });
});

describe('组装提交体', () => {
  it('只提交勾选的菜，数值一律以字符串下发', () => {
    const payload = buildSavePayload(validValues(), [
      selectedRow(),
      selectedRow({ dishId: 'b', selected: false, servings: null }),
    ]);

    expect(payload.dishes).toHaveLength(1);
    expect(payload.dishes?.[0]).toMatchObject({
      dish_id: 'a',
      servings_produced: '451',
      leftover_ratio: '0.05',
    });
    expect(payload.oil_total_g).toBe('6242.84');
    expect(payload.diner_count).toBe(885);
  });

  it('没填的剩餐重量提交为空，而不是 0——没填和真的没剩是两回事', () => {
    const payload = buildSavePayload(validValues(), [selectedRow()]);

    expect(payload.leftover_weight_g).toBeNull();
  });

  it('没填的油盐糖提交为空，而不是 0', () => {
    const payload = buildSavePayload(
      { ...validValues(), oilTotalG: null, saltTotalG: null, sugarTotalG: null },
      [selectedRow()],
    );

    expect(payload.oil_total_g).toBeNull();
    expect(payload.salt_total_g).toBeNull();
    expect(payload.sugar_total_g).toBeNull();
  });
});

it('回执文案把勾了几道菜与重算结果都说清楚', () => {
  expect(describeSaved({ dish_count: 5, nutrition_rows: 10 })).toBe(
    '已保存 5 道菜，重算了 10 条营养结果',
  );
});

describe('计划份数怎么显示', () => {
  it('按整数说，不把预测出来的小数摆到录入员面前', () => {
    expect(formatPlannedServings('812.36')).toBe('812');
    expect(formatPlannedServings('1200.00')).toBe('1,200');
  });

  it('没有计划就说没有，不显示成 0 份', () => {
    expect(formatPlannedServings(null)).toBeNull();
    expect(formatPlannedServings('')).toBeNull();
  });
});

it('空字符串按没填处理，而不是当成 0', () => {
  expect(toNumber('')).toBeNull();
  expect(toNumber(null)).toBeNull();
  expect(toNumber('0')).toBe(0);
});

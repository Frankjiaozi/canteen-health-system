import { describe, expect, it } from 'vitest';
import { buildIngredientQuery, formatNutrient, percentToRatio, ratioToPercent } from './query';

describe('buildIngredientQuery', () => {
  it('去掉首尾空格的搜索词', () => {
    const query = buildIngredientQuery({ page: 1, pageSize: 20, keyword: '  西兰花  ' });

    expect(query.keyword).toBe('西兰花');
  });

  it('空搜索词不进查询串', () => {
    expect(buildIngredientQuery({ page: 1, pageSize: 20, keyword: '   ' })).not.toHaveProperty(
      'keyword',
    );
  });

  it('未选类别时不带类别参数', () => {
    expect(buildIngredientQuery({ page: 1, pageSize: 20, category: null })).not.toHaveProperty(
      'category',
    );
  });

  it('带上类别与停用标记', () => {
    const query = buildIngredientQuery({
      page: 2,
      pageSize: 50,
      category: 'VEGETABLE',
      includeInactive: true,
    });

    expect(query).toEqual({
      page: 2,
      page_size: 50,
      category: 'VEGETABLE',
      include_inactive: true,
    });
  });
});

describe('formatNutrient', () => {
  it('按指定小数位展示', () => {
    expect(formatNutrient('25.50', 2)).toBe('25.50');
    expect(formatNutrient('7.4', 3)).toBe('7.400');
  });

  it('缺失数据显示为破折号而不是 0', () => {
    expect(formatNutrient(null, 2)).toBe('—');
    expect(formatNutrient(undefined, 2)).toBe('—');
    expect(formatNutrient('', 2)).toBe('—');
  });
});

describe('可食部比例换算', () => {
  it('比例与百分比可以来回换算', () => {
    expect(ratioToPercent('0.8500')).toBe(85);
    expect(percentToRatio(85)).toBe('0.8500');
  });

  it('空值返回 null', () => {
    expect(ratioToPercent(null)).toBeNull();
    expect(percentToRatio(null)).toBeNull();
  });
});

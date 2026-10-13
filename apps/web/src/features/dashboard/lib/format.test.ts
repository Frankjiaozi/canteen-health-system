import { describe, expect, it } from 'vitest';
import { RANGE_OPTIONS, formatPercent, toNumber, trimDecimal } from './format';

describe('看板数值格式化', () => {
  it('去掉小数末尾多余的零', () => {
    expect(trimDecimal('5.000')).toBe('5');
    expect(trimDecimal('1.950')).toBe('1.95');
    expect(trimDecimal(null)).toBe('—');
  });

  it('比例转百分比', () => {
    expect(formatPercent('0.5000')).toBe('50.0%');
    expect(formatPercent('1.0000')).toBe('100.0%');
    expect(formatPercent(null)).toBe('—');
  });

  it('字符串转图表用的数值', () => {
    expect(toNumber('276.80')).toBe(276.8);
    expect(toNumber('0.0804', 4)).toBe(0.0804);
    expect(toNumber(null)).toBe(0);
    expect(toNumber('不是数字')).toBe(0);
  });

  it('时间范围选项覆盖 7 / 14 / 30 天', () => {
    expect(RANGE_OPTIONS.map((option) => option.value)).toEqual([7, 14, 30]);
  });
});

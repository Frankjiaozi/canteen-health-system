import { describe, expect, it } from 'vitest';
import type { HolidayRead } from '../types';
import {
  describeCoverage,
  describeMape,
  formatQuantity,
  formatServings,
  summarizeHolidays,
} from './format';

describe('回测结论', () => {
  it('低于达标线算达标', () => {
    const verdict = describeMape('0.0769', '0.20');

    expect(verdict.ok).toBe(true);
    expect(verdict.text).toContain('7.7%');
  });

  it('超出达标线要说不达标', () => {
    const verdict = describeMape('0.3723', '0.20');

    expect(verdict.ok).toBe(false);
    expect(verdict.text).toContain('超过达标线');
  });

  it('算不出 MAPE 时不能算达标——那会把没测过说成测过了', () => {
    expect(describeMape(null, '0.20').ok).toBe(false);
    expect(describeMape(null, '0.20').text).toContain('算不出');
  });
});

describe('回测覆盖', () => {
  it('说明有多少天真的算出了结果，以及为什么少', () => {
    expect(describeCoverage(50, 56)).toContain('50 天');
    expect(describeCoverage(50, 56)).toContain('前 6 天的历史不足');
  });

  it('全都算得出时不必解释', () => {
    expect(describeCoverage(56, 56)).toContain('每天都有足够历史');
  });
});

describe('数值展示', () => {
  it('份数按整数显示', () => {
    expect(formatServings('471.33')).toBe('471');
    expect(formatServings('943.5')).toBe('944');
  });

  it('克重去掉多余的小数位', () => {
    expect(formatQuantity('37230.000')).toBe('37230');
    expect(formatQuantity('3216.570')).toBe('3216.6');
  });
});

describe('日历核对提示', () => {
  const holiday = (overrides: Partial<HolidayRead>): HolidayRead =>
    ({
      id: 'h1',
      date: '2026-10-01',
      name: '国庆节',
      kind: 'HOLIDAY',
      kind_label: '放假',
      is_verified: false,
      source_note: null,
      ...overrides,
    }) as HolidayRead;

  it('未核对时点名是哪几条，并说清它们已经在影响预测', () => {
    const summary = summarizeHolidays([holiday({}), holiday({ id: 'h2', name: '中秋节' })]);

    expect(summary.unverified).toHaveLength(2);
    expect(summary.text).toContain('国庆节、中秋节');
    expect(summary.text).toContain('已经在参与预测修正');
  });

  it('全部核对通过后不再提醒', () => {
    expect(summarizeHolidays([holiday({ is_verified: true })]).text).toContain('全部已核对');
  });

  it('没有日历数据时说清后果', () => {
    expect(summarizeHolidays([]).text).toContain('不做节假日修正');
  });
});

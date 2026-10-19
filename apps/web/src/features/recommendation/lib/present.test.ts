import { describe, expect, it } from 'vitest';
import type { NutrientGap, SuggestionReason } from '../types';
import { decisionLabel, describeGap, describeGapStatus, reasonLabel } from './present';

const gap = (overrides: Partial<NutrientGap>): NutrientGap =>
  ({
    code: 'energy_kcal',
    label: '能量',
    unit: '千卡',
    target_text: '720 ~ 800千卡',
    actual: '760',
    status: 'ok',
    gap: '0',
    note: null,
    ...overrides,
  }) as NutrientGap;

describe('差距的状态', () => {
  it('达标时说落在区间内', () => {
    expect(describeGapStatus(gap({})).tone).toBe('ok');
    expect(describeGap(gap({}))).toContain('落在');
  });

  it('营养不够时说清还差多少', () => {
    const row = gap({ status: 'under', actual: '690', gap: '30' });

    expect(describeGapStatus(row).label).toBe('低于目标');
    expect(describeGap(row)).toContain('还差 30千卡');
  });

  it('油盐糖超的是每日上限，措辞不能混成「超出推荐量」', () => {
    const salt = gap({
      code: 'SALT',
      label: '食盐',
      unit: 'g',
      status: 'over',
      actual: '6',
      gap: '1',
      target_text: '≤ 5.000g',
    });

    expect(describeGapStatus(salt).label).toBe('超出每日上限');
    expect(describeGap(salt)).toContain('超出 1g');
  });
});

describe('推荐理由的标签', () => {
  it('已知类别给中文，未知类别原样显示', () => {
    expect(reasonLabel({ kind: 'nutrition', text: '' } as SuggestionReason)).toBe('营养');
    expect(reasonLabel({ kind: 'popularity', text: '' } as SuggestionReason)).toBe('受欢迎度');
    expect(reasonLabel({ kind: 'unknown', text: '' } as SuggestionReason)).toBe('unknown');
  });
});

describe('采纳状态', () => {
  it('三种状态各自的文案与语气', () => {
    expect(decisionLabel('ACCEPTED')).toEqual({ text: '已采纳', tone: 'ok' });
    expect(decisionLabel('REJECTED').tone).toBe('bad');
    expect(decisionLabel('PENDING').tone).toBe('pending');
  });
});

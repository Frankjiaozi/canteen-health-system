import { describe, expect, it } from 'vitest';
import type { SampleResult, SamplingCandidate } from '../types';
import {
  defaultMeasured,
  describeSampleResult,
  deviationOf,
  formatNumber,
  formatRatio,
  hasThreeValues,
} from './compare';

describe('偏差判断', () => {
  it('算出相对偏差并按阈值标出来', () => {
    const small = deviationOf('105', '100');
    const big = deviationOf('130', '100');

    expect(small.ratio).toBeCloseTo(0.05);
    expect(small.notable).toBe(false);
    expect(big.ratio).toBeCloseTo(0.3);
    expect(big.notable).toBe(true);
  });

  it('推算值为 0 时不给相对偏差——除以 0 得出的百分比会误导人', () => {
    const deviation = deviationOf('5', '0');

    expect(deviation.ratio).toBeNull();
    expect(deviation.delta).toBe(5);
    expect(deviation.notable).toBe(true);
  });

  it('数字缺失时不装作没有偏差', () => {
    // 空字符串不是 0：Number('') 等于 0，直接算会得出「实测比推算少了整整 100%」
    expect(deviationOf('', '100').ratio).toBeNull();
    expect(deviationOf('', '100').notable).toBe(false);
    expect(deviationOf('100', '').ratio).toBeNull();
  });
});

describe('展示格式', () => {
  it('缺数据显示破折号，而不是 0', () => {
    expect(formatNumber(null, 2)).toBe('—');
    expect(formatNumber('193.567', 2)).toBe('193.57');
  });

  it('相对偏差带正负号', () => {
    expect(formatRatio(0.1234)).toBe('+12.3%');
    expect(formatRatio(-0.05)).toBe('-5.0%');
    expect(formatRatio(null)).toBe('—');
  });
});

describe('三值齐备的判断', () => {
  const base = {
    dish_id: 'a',
    dish_name: '土豆炖牛肉',
    category_label: '荤菜',
    cooking_method_label: '炖',
    theoretical: null,
    calibrated: null,
    sampled: null,
    applied: null,
    suspect_recipe: null,
  } as unknown as SamplingCandidate;

  it('三个都拿到才算齐', () => {
    expect(hasThreeValues(base)).toBe(false);
    expect(
      hasThreeValues({
        ...base,
        theoretical: {},
        calibrated: {},
        sampled: {},
      } as SamplingCandidate),
    ).toBe(true);
  });
});

describe('实测的默认值', () => {
  it('直接带出校准值，录入员只改相差的那几项', () => {
    const candidate = {
      theoretical: { energy_kcal: '191.42' },
      calibrated: { energy_kcal: '193.57' },
      sampled: null,
    } as unknown as SamplingCandidate;

    expect(defaultMeasured(candidate).energy_kcal).toBe(193.57);
  });

  it('没有校准值时退回理论值', () => {
    const candidate = {
      theoretical: { energy_kcal: '191.42' },
      calibrated: null,
      sampled: null,
    } as unknown as SamplingCandidate;

    expect(defaultMeasured(candidate).energy_kcal).toBe(191.42);
  });
});

describe('抽样结果文案', () => {
  const result = {
    overall_factor: '1.0738',
    suspect_recipe: false,
    note: '',
  } as unknown as SampleResult;

  it('正常套用时说明系数作用在哪一层', () => {
    expect(describeSampleResult(result)).toContain('1.0738');
    expect(describeSampleResult(result)).toContain('调味料');
  });

  it('疑似配方有误时给出可照做的下一步', () => {
    const suspect = { ...result, suspect_recipe: true } as SampleResult;

    expect(describeSampleResult(suspect)).toContain('配方');
    expect(describeSampleResult(suspect)).toContain('未套用');
  });
});

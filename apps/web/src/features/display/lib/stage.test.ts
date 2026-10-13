import { describe, expect, it } from 'vitest';
import { STAGE_HEIGHT, STAGE_WIDTH, computeStageLayout } from './stage';
import { describeStatus, describeTarget, trimDecimal } from './standards';

describe('computeStageLayout', () => {
  it('基准分辨率下比例为 1 且不需要偏移', () => {
    const layout = computeStageLayout(STAGE_WIDTH, STAGE_HEIGHT);

    expect(layout.scale).toBe(1);
    expect(layout.offsetX).toBe(0);
    expect(layout.offsetY).toBe(0);
  });

  it('竖向更窄时按高度收缩，保证不溢出', () => {
    const layout = computeStageLayout(1600, 720);

    // 1600/1920 ≈ 0.833、720/1080 ≈ 0.667 → 取较小值
    expect(layout.scale).toBeCloseTo(720 / STAGE_HEIGHT, 5);
    expect(STAGE_WIDTH * layout.scale).toBeLessThanOrEqual(1600);
    expect(STAGE_HEIGHT * layout.scale).toBeLessThanOrEqual(720);
  });

  it('横向更窄时按宽度收缩', () => {
    const layout = computeStageLayout(1280, 1080);

    expect(layout.scale).toBeCloseTo(1280 / STAGE_WIDTH, 5);
    expect(STAGE_WIDTH * layout.scale).toBeLessThanOrEqual(1280);
  });

  it('缩放后居中，左右偏移相等', () => {
    const layout = computeStageLayout(1280, 800);

    expect(layout.offsetX).toBeCloseTo((1280 - STAGE_WIDTH * layout.scale) / 2, 5);
    expect(layout.offsetY).toBeCloseTo((800 - STAGE_HEIGHT * layout.scale) / 2, 5);
  });

  it('视口尺寸为 0 时退回默认值，不产生 NaN', () => {
    expect(computeStageLayout(0, 0)).toEqual({ scale: 1, offsetX: 0, offsetY: 0 });
  });
});

describe('基准对照文案', () => {
  it('区间、上限、下限分别有对应说法', () => {
    const base = {
      code: 'EDIBLE_OIL',
      label: '烹调油',
      unit: 'g',
      status: 'ok',
      source: '《中国居民膳食指南（2022）》',
      source_quote: null,
      actual: '5.28',
    };

    expect(describeTarget({ ...base, target_min: '25.000', target_max: '30.000' })).toBe(
      '每日 25 ~ 30 g',
    );
    expect(describeTarget({ ...base, target_min: null, target_max: '5.000' })).toBe(
      '每日不超过 5 g',
    );
    expect(describeTarget({ ...base, target_min: '12.000', target_max: null })).toBe(
      '每日不少于 12 g',
    );
  });

  it('状态用不同的中文与颜色区分不足和超标', () => {
    expect(describeStatus('over')).toEqual({ color: '#ff7875', text: '超出上限' });
    expect(describeStatus('under').text).toBe('低于推荐');
    expect(describeStatus('ok').text).toBe('达标');
    expect(describeStatus('unknown').text).toBe('暂无数据');
  });

  it('去掉小数末尾多余的零', () => {
    expect(trimDecimal('5.000')).toBe('5');
    expect(trimDecimal('1.790')).toBe('1.79');
    expect(trimDecimal('12')).toBe('12');
  });
});

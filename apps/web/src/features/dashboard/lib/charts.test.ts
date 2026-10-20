import { describe, expect, it } from 'vitest';
import { buildTrendOption, buildComplianceOption, buildWasteOption } from './charts';
import type { TrendsResponse, ComplianceResponse, WasteResponse } from '../types';

describe('图表保留完整日历，缺失与真实零值分开', () => {
  it.each([7, 14, 30])('%i 天窗口显示全部日期且不把缺记录画成 0', (days) => {
    const start = '2026-10-01';
    const end = new Date(Date.UTC(2026, 9, days)).toISOString().slice(0, 10);
    const response: TrendsResponse = {
      days,
      start,
      end,
      targets: [],
      points: [
        {
          date: '2026-10-02',
          diner_count: 0,
          oil_total_g: '0',
          salt_total_g: '0',
          sugar_total_g: '0',
          oil_per_capita_g: '0',
          salt_per_capita_g: '0',
          sugar_per_capita_g: '0',
        },
      ],
    };
    const option = buildTrendOption(response);
    expect(option.xAxis.data).toHaveLength(days);
    expect(option.xAxis.data.at(-1)).toBe(response.end.slice(5));
    expect(option.series[0].data[0]).toBeNull();
    expect(option.series[0].data[1]).toBe(0);
    expect(option.series[0].data.at(-1)).toBeNull();
    if (days <= 14) expect(option.xAxis.axisLabel.interval).toBe(0);
  });
  it('浪费率与达标率的未知值也保留断点', () => {
    const waste: WasteResponse = {
      days: 1,
      start: '2026-10-20',
      end: '2026-10-20',
      points: [],
      average_ratio: null,
    };
    expect(buildWasteOption(waste).series[0].data).toEqual([null]);
    expect(buildWasteOption(waste).series[1].data).toEqual([null]);
    const compliance: ComplianceResponse = {
      days: 1,
      start: waste.start,
      end: waste.end,
      points: [],
      overall_rate: null,
    };
    expect(buildComplianceOption(compliance).series[0].data).toEqual([null]);
  });
});

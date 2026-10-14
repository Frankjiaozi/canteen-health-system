import type { SampleResult, SamplingCandidate } from '../types';

/** 五项指标的展示元数据，与后端 `app/shared/nutrients.py` 一一对应。 */
export const NUTRIENT_ROWS = [
  { field: 'energy_kcal', code: 'ENERGY', label: '能量', unit: '千卡', digits: 2 },
  { field: 'protein_g', code: 'PROTEIN', label: '蛋白质', unit: '克', digits: 3 },
  { field: 'fat_g', code: 'FAT', label: '脂肪', unit: '克', digits: 3 },
  { field: 'carb_g', code: 'CARBOHYDRATE', label: '碳水化合物', unit: '克', digits: 3 },
  { field: 'sodium_mg', code: 'SODIUM', label: '钠', unit: '毫克', digits: 2 },
] as const;

export type NutrientField = (typeof NUTRIENT_ROWS)[number]['field'];

export interface Deviation {
  /** 实测与推算的差（实测 − 推算） */
  delta: number;
  /** 相对偏差，推算值为 0 时没有意义，返回 null */
  ratio: number | null;
  /** 偏差是否大到需要留意 */
  notable: boolean;
}

/** 偏差超过这个比例就标出来，与后端判定「可疑」的口径保持一致。 */
export const NOTABLE_DEVIATION = 0.1;

export function deviationOf(measured: string, computed: string): Deviation {
  // 空字符串要先挡掉：Number('') 是 0，会被当成「实测为 0」，
  const left = Number(measured);
  const right = Number(computed);
  if (measured === '' || computed === '' || Number.isNaN(left) || Number.isNaN(right)) {
    return { delta: 0, ratio: null, notable: false };
  }
  const delta = left - right;
  if (right === 0) {
    return { delta, ratio: null, notable: delta !== 0 };
  }
  const ratio = delta / right;
  return { delta, ratio, notable: Math.abs(ratio) > NOTABLE_DEVIATION };
}

export function formatNumber(value: string | null | undefined, digits: number): string {
  if (value === null || value === undefined) return '—';
  const parsed = Number(value);
  return Number.isNaN(parsed) ? '—' : parsed.toFixed(digits);
}

export function formatRatio(ratio: number | null): string {
  if (ratio === null) return '—';
  const percent = ratio * 100;
  return `${percent >= 0 ? '+' : ''}${percent.toFixed(1)}%`;
}

/** 这道菜是不是已经把三个值凑齐了。 */
export function hasThreeValues(candidate: SamplingCandidate): boolean {
  return (
    candidate.theoretical !== null && candidate.calibrated !== null && candidate.sampled !== null
  );
}

/** 抽样结果的一句话结论，直接给录入员看。 */
export function describeSampleResult(result: SampleResult): string {
  if (result.suspect_recipe) {
    return `实测与推算差距超出调味料能解释的范围，已保留实测证据但未套用系数（反推系数 ${
      result.overall_factor ?? '—'
    }），建议核对这道菜的配方用量`;
  }
  return `已套用整体系数 ${result.overall_factor ?? '—'}，作用在调味料贡献上；理论值保持不变`;
}

/** 未录入实测值时的默认值：直接带出推算值，录入员只需改动相差的那几项。 */
export function defaultMeasured(
  candidate: SamplingCandidate,
): Record<NutrientField, number | null> {
  const baseline = candidate.calibrated ?? candidate.theoretical;
  return Object.fromEntries(
    NUTRIENT_ROWS.map((row) => [row.field, baseline ? Number(baseline[row.field]) : null]),
  ) as Record<NutrientField, number | null>;
}

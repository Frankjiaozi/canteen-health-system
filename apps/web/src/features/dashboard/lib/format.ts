// 去小数末尾多余的零：5.000 → 5
export function trimDecimal(value: string | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—';
  if (!value.includes('.')) return value;
  return value.replace(/0+$/, '').replace(/\.$/, '');
}

// 0.5000 → 50.0%
export function formatPercent(value: string | null | undefined, digits = 1): string {
  if (value === null || value === undefined || value === '') return '—';
  const parsed = Number(value);
  if (Number.isNaN(parsed)) return '—';
  return `${(parsed * 100).toFixed(digits)}%`;
}

// 截断到指定小数位后转数字，供图表使用（ECharts 需要数值而不是字符串）
export function toNumber(value: string | null | undefined, digits = 2): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return null;
  return Number(parsed.toFixed(digits));
}

export const RANGE_OPTIONS = [
  { label: '近 7 天', value: 7 },
  { label: '近 14 天', value: 14 },
  { label: '近 30 天', value: 30 },
] as const;

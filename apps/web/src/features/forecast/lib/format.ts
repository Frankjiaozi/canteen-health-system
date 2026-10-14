import type { DishForecast, HolidayRead } from '../types';

export interface MapeVerdict {
  ok: boolean;
  text: string;
}

/** 回测结论。没有 MAPE 时说「算不出」，而不是当成达标。 */
export function describeMape(mape: string | null, target: string): MapeVerdict {
  if (mape === null) {
    return { ok: false, text: '可回测的样本不足，算不出 MAPE' };
  }
  const value = Number(mape);
  const line = Number(target);
  const percent = (value * 100).toFixed(1);
  if (Number.isNaN(value) || Number.isNaN(line)) {
    return { ok: false, text: 'MAPE 数据异常' };
  }
  return value <= line
    ? { ok: true, text: `平均绝对百分比误差 ${percent}%，达标线 ${(line * 100).toFixed(0)}%` }
    : { ok: false, text: `平均绝对百分比误差 ${percent}%，超过达标线 ${(line * 100).toFixed(0)}%` };
}

/** 回测覆盖情况：8 周数据只能回测后段，这一点要说出来而不是藏着。 */
export function describeCoverage(usableDays: number, days: number): string {
  if (days <= 0) return '回测区间为空';
  const missing = days - usableDays;
  if (missing <= 0) return `回测 ${days} 天，每天都有足够历史可参照`;
  return `回测 ${days} 天，其中 ${usableDays} 天有足够历史可参照（前 ${missing} 天的历史不足）`;
}

/** 份数按整数看更自然：厨师不会去数 471.33 份。 */
export function formatServings(value: string): string {
  const parsed = Number(value);
  if (Number.isNaN(parsed)) return value;
  return Math.round(parsed).toLocaleString('zh-CN');
}

export function formatAmount(value: string | null | undefined): string {
  if (value === null || value === undefined) return '—';
  const parsed = Number(value);
  return Number.isNaN(parsed) ? '—' : parsed.toFixed(2);
}

/** 数量按克计，三位小数在这里是噪声，最多留一位。 */
export function formatQuantity(value: string): string {
  const parsed = Number(value);
  if (Number.isNaN(parsed)) return value;
  return Number.isInteger(parsed) ? String(parsed) : parsed.toFixed(1);
}

export function describeDishBasis(dish: DishForecast): string {
  return `${dish.basis_label}（${dish.samples.length} 个样本）`;
}

export interface HolidaySummary {
  unverified: HolidayRead[];
  text: string;
}

/** 日历核对状态的提示语。未核对的条目必须点名，不能只报一个数字。 */
export function summarizeHolidays(items: HolidayRead[]): HolidaySummary {
  const unverified = items.filter((item) => !item.is_verified);
  if (items.length === 0) {
    return { unverified, text: '这一年还没有内置日历，预测将不做节假日修正' };
  }
  if (unverified.length === 0) {
    return { unverified, text: `${items.length} 条日历全部已核对` };
  }
  return {
    unverified,
    text: `还有 ${unverified.length} 条日历未核对（${unverified
      .map((item) => item.name)
      .join('、')}）。这些日期已经在参与预测修正，请对照国务院办公厅通知确认后再标记为已核对`,
  };
}

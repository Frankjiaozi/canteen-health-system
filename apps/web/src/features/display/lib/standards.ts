import type { StandardComparison } from '../types';

export type StandardStatus = 'ok' | 'over' | 'under' | 'unknown';

export interface StatusStyle {
  color: string;
  text: string;
}

// 基准对照的展示口径。
//
// 「不足」与「超标」在营养语境里是两件事：烹调油低于推荐区间是供给不足，
// 食盐超出上限才是要警惕的方向。用不同颜色区分，不笼统地叫「不达标」。
export function describeStatus(status: string): StatusStyle {
  switch (status as StandardStatus) {
    case 'ok':
      return { color: '#2f7d4f', text: '达标' };
    case 'over':
      return { color: '#b5473a', text: '超出上限' };
    case 'under':
      return { color: '#a8711e', text: '低于推荐' };
    default:
      return { color: '#7a8a7e', text: '暂无数据' };
  }
}

// 去掉小数末尾多余的零：5.000 → 5，1.790 → 1.79
export function trimDecimal(value: string): string {
  if (!value.includes('.')) return value;
  return value.replace(/0+$/, '').replace(/\.$/, '');
}

// 把基准画成一句人话，例如「每日不超过 5 克」
export function describeTarget(standard: StandardComparison): string {
  const min = standard.target_min;
  const max = standard.target_max;
  if (min && max) return `每日 ${trimDecimal(min)} ~ ${trimDecimal(max)} ${standard.unit}`;
  if (max) return `每日不超过 ${trimDecimal(max)} ${standard.unit}`;
  if (min) return `每日不少于 ${trimDecimal(min)} ${standard.unit}`;
  return '暂无基准';
}

export function formatActual(standard: StandardComparison): string {
  if (standard.actual === null || standard.actual === undefined) return '—';
  return trimDecimal(standard.actual);
}

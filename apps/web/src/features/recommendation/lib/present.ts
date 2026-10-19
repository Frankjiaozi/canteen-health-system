import type { NutrientGap, SuggestionReason } from '../types';

/** 差距的状态文案与颜色语义。只给「达标 / 不达标」的标签不算完成，缺口要摆出来。 */
export interface GapStyle {
  label: string;
  tone: 'ok' | 'over' | 'under';
}

export function describeGapStatus(gap: NutrientGap): GapStyle {
  const isSeasoning = ['EDIBLE_OIL', 'SALT', 'ADDED_SUGAR'].includes(gap.code);
  if (gap.status === 'ok') {
    return { label: '达标', tone: 'ok' };
  }
  if (gap.status === 'over') {
    return {
      // 油盐糖超的是「每日上限」，说成「超出目标」会让人以为超了推荐量
      label: isSeasoning ? '超出每日上限' : '超出目标',
      tone: 'over',
    };
  }
  return { label: '低于目标', tone: 'under' };
}

/** 差距一行话：说清差多少、差在哪个方向。 */
export function describeGap(gap: NutrientGap): string {
  if (gap.status === 'ok') {
    return `实际 ${gap.actual}${gap.unit}，落在 ${gap.target_text} 内`;
  }
  const direction = gap.status === 'over' ? '超出' : '还差';
  return `实际 ${gap.actual}${gap.unit}，${direction} ${gap.gap}${gap.unit}（目标 ${gap.target_text}）`;
}

const REASON_LABELS: Record<string, string> = {
  nutrition: '营养',
  cost: '成本',
  popularity: '受欢迎度',
  constraint: '约束',
  variety: '多样性',
};

export function reasonLabel(reason: SuggestionReason): string {
  return REASON_LABELS[reason.kind] ?? reason.kind;
}

export function decisionLabel(status: string): { text: string; tone: 'pending' | 'ok' | 'bad' } {
  if (status === 'ACCEPTED') return { text: '已采纳', tone: 'ok' };
  if (status === 'REJECTED') return { text: '已否决', tone: 'bad' };
  return { text: '待确认', tone: 'pending' };
}

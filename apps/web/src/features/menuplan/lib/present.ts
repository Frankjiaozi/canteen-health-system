import { formatAmount, formatServings } from '@/features/forecast/lib/format';
import type { IngredientRequirement, MenuPlanBatchDay, MenuPlanDish } from '../types';

/**
 * 「这一份份数是怎么来的」。
 *
 * 采购量直接由份数乘出来，所以份数的来源必须摆在明面上：能预测的说清用的哪套依据，
 * 预测不出来的**如实说**是按「每人一份」估的，不能给一个看不出来源的数字。
 */
export interface PredictionOrigin {
  text: string;
  tone: 'forecast' | 'fallback';
}

export function describePredictionOrigin(dish: MenuPlanDish): PredictionOrigin {
  if (dish.prediction_fallback || !dish.predicted_servings) {
    return { text: '历史不足，按「每人一份」估算', tone: 'fallback' };
  }
  const basis = dish.predicted_basis_label ? `，${dish.predicted_basis_label}` : '';
  return { text: `${formatServings(dish.predicted_servings)} 份${basis}`, tone: 'forecast' };
}

export interface PurchaseSummary {
  text: string;
  tone: 'ok' | 'over' | 'incomplete';
  note: string;
}

/**
 * 采购单的合计与预算比对。
 *
 * 缺单价时必须说出来：那几项的金额算不出来，合计**必然偏低**，
 * 只给一个偏小的数字会让人以为预算很宽松。
 */
export function summarizePurchase(
  rows: IngredientRequirement[],
  totalCost: string | null | undefined,
  budget: string,
): PurchaseSummary {
  const unpriced = rows.filter((row) => row.estimated_cost === null).map((row) => row.name);
  const text = `采购金额 ${formatAmount(totalCost)} 元 / 预算 ${formatAmount(budget)} 元`;

  if (unpriced.length > 0) {
    return {
      text,
      tone: 'incomplete',
      note: `有 ${unpriced.length} 项未录入单价（${unpriced.join('、')}），合计金额偏低`,
    };
  }
  const total = Number(totalCost ?? '');
  const cap = Number(budget);
  if (Number.isNaN(total) || Number.isNaN(cap)) {
    return { text, tone: 'incomplete', note: '金额数据异常，无法与预算比对' };
  }
  return total > cap
    ? { text, tone: 'over', note: `超出预算 ${(total - cap).toFixed(2)} 元` }
    : { text, tone: 'ok', note: '' };
}

export type BatchTone = 'ok' | 'skipped' | 'bad';

/** 批量结果里一天的状态色。四种状态各有各的语气，不混成一个「成功/失败」。 */
export function batchStatusTone(status: string): BatchTone {
  if (status === 'GENERATED' || status === 'IMPORTED') return 'ok';
  if (status === 'SKIPPED') return 'skipped';
  return 'bad';
}

/**
 * 导入之后把两批结果合起来看。

 * 导入返回的每一行只有状态与条数（它不重算菜单），而用户还想看到「这一天排了什么菜」，
 * 所以按日期合：状态以导入那次为准，菜品与金额沿用生成那次。
 */
export function mergeBatchStatuses(
  generated: MenuPlanBatchDay[],
  imported: MenuPlanBatchDay[],
): MenuPlanBatchDay[] {
  const byDate = new Map(imported.map((row) => [row.date, row]));
  return generated.map((row) => {
    const latest = byDate.get(row.date);
    if (!latest) return row;
    return {
      ...row,
      status: latest.status,
      status_label: latest.status_label,
      reason: latest.reason,
      suggestion_id: latest.suggestion_id ?? row.suggestion_id,
      dish_count: latest.dish_count || row.dish_count,
      nutrition_rows: latest.nutrition_rows,
    };
  });
}

import type { DailyLogSheet, DailyLogWrite, MealType } from '../types';

/** 表格里一行菜的可编辑状态。 */
export interface SheetRow {
  dishId: string;
  /** 今天这餐真的供应了它吗——勾选即写入当天菜单日 */
  selected: boolean;
  servings: number | null;
  leftoverRatio: number | null;
  isSubstituted: boolean;
  substitutionNote: string | null;
}

export interface SheetFormValues {
  dinerCount: number | null;
  oilTotalG: number | null;
  saltTotalG: number | null;
  sugarTotalG: number | null;
  leftoverWeightG: number | null;
  note: string | null;
  anomalyFlags: string[];
  mealType: MealType;
}

/** 采集单打开时的初始状态：已保存的沿用库里的值，没保存过的按「未勾选」处理。 */
export function initialRows(sheet: DailyLogSheet): SheetRow[] {
  return sheet.dishes.map((dish) => ({
    dishId: dish.dish_id,
    selected: dish.selected,
    servings: toNumber(dish.servings_produced),
    leftoverRatio: toNumber(dish.leftover_ratio),
    isSubstituted: dish.is_substituted,
    substitutionNote: dish.substitution_note ?? null,
  }));
}

export function initialFormValues(sheet: DailyLogSheet): SheetFormValues {
  return {
    dinerCount: sheet.diner_count ?? null,
    oilTotalG: toNumber(sheet.oil_total_g),
    saltTotalG: toNumber(sheet.salt_total_g),
    sugarTotalG: toNumber(sheet.sugar_total_g),
    leftoverWeightG: toNumber(sheet.leftover_weight_g),
    note: sheet.note ?? null,
    anomalyFlags: sheet.anomaly_flags.filter((flag) => !flag.system).map((flag) => flag.value),
    mealType: sheet.meal_type,
  };
}

export function toNumber(value: string | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(value);
  return Number.isNaN(parsed) ? null : parsed;
}

/**
 * 计划份数按整数说。
 *
 * 它是预测算出来的小数（812.36），但录入员拿它对标时只需要「大概八百份」——
 * 把小数照搬出来只会让人以为要按小数出餐。取不到（没排菜单、预测不出来）时返回空，
 * 界面上就不显示这一项，而不是显示「计划 0 份」。
 */
export function formatPlannedServings(value: string | null | undefined): string | null {
  const parsed = toNumber(value);
  if (parsed === null) return null;
  return Math.round(parsed).toLocaleString('zh-CN');
}

/**
 * 提交前的校验。返回一句能照做的中文提示；全部通过时返回 null。
 *
 * 这些规则与后端一致（后端也会再拦一次）——放在前端只是为了让录入员当场知道哪里没填，
 * 而不是提交之后收到一条 422。
 */
export function validateSheet(values: SheetFormValues, rows: SheetRow[]): string | null {
  const selected = rows.filter((row) => row.selected);
  if (selected.length === 0) {
    return '至少勾选一道今天供应的菜品';
  }
  if (values.dinerCount === null || values.dinerCount <= 0) {
    return '请填写就餐人次，人均摄入要靠它才算得出来';
  }
  const missing = selected.filter((row) => row.servings === null);
  if (missing.length > 0) {
    return `还有 ${missing.length} 道勾选的菜没填出餐份数`;
  }
  const badRatio = selected.find(
    (row) => row.leftoverRatio !== null && (row.leftoverRatio < 0 || row.leftoverRatio > 1),
  );
  if (badRatio) {
    return '剩余比例要在 0 到 1 之间，比如剩两成填 0.2';
  }
  return null;
}

/** 把表单状态组装成提交体。 */
export function buildSavePayload(values: SheetFormValues, rows: SheetRow[]): DailyLogWrite {
  return {
    meal_type: values.mealType,
    diner_count: values.dinerCount ?? 0,
    oil_total_g: String(values.oilTotalG ?? 0),
    salt_total_g: String(values.saltTotalG ?? 0),
    sugar_total_g: String(values.sugarTotalG ?? 0),
    leftover_weight_g: values.leftoverWeightG === null ? null : String(values.leftoverWeightG),
    note: values.note,
    anomaly_flags: values.anomalyFlags as DailyLogWrite['anomaly_flags'],
    dishes: rows
      .filter((row) => row.selected)
      .map((row) => ({
        dish_id: row.dishId,
        servings_produced: String(row.servings ?? 0),
        leftover_ratio: row.leftoverRatio === null ? null : String(row.leftoverRatio),
        leftover_weight_g: null,
        is_substituted: row.isSubstituted,
        substitution_note: row.substitutionNote,
        note: null,
      })),
  };
}

/** 保存成功后的回执文案。 */
export function describeSaved(result: { dish_count: number; nutrition_rows: number }): string {
  return `已保存 ${result.dish_count} 道菜，重算了 ${result.nutrition_rows} 条营养结果`;
}

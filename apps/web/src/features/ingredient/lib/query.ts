import type { IngredientCategory } from '../types';

export interface IngredientQueryParams {
  page: number;
  pageSize: number;
  keyword?: string;
  category?: IngredientCategory | null;
  includeInactive?: boolean;
}

/** 接口查询串。抽出来是为了能直接做单元测试，也避免各处拼串写法不一致。 */
export interface IngredientQuery {
  page: number;
  page_size: number;
  keyword?: string;
  category?: IngredientCategory;
  include_inactive: boolean;
}

export function buildIngredientQuery({
  page,
  pageSize,
  keyword,
  category,
  includeInactive = false,
}: IngredientQueryParams): IngredientQuery {
  const query: IngredientQuery = {
    page,
    page_size: pageSize,
    include_inactive: includeInactive,
  };

  const trimmed = keyword?.trim();
  if (trimmed) {
    query.keyword = trimmed;
  }
  if (category) {
    query.category = category;
  }
  return query;
}

/** 展示营养值：空值显示为「—」，而不是 0——缺数据与真的为零是两码事。 */
export function formatNutrient(value: string | null | undefined, digits: number): string {
  if (value === null || value === undefined || value === '') {
    return '—';
  }
  const parsed = Number(value);
  if (Number.isNaN(parsed)) {
    return '—';
  }
  return parsed.toFixed(digits);
}

/** 可食部比例以百分比展示，编辑时也按百分比输入。 */
export function ratioToPercent(ratio: string | null | undefined): number | null {
  if (ratio === null || ratio === undefined || ratio === '') {
    return null;
  }
  const parsed = Number(ratio);
  return Number.isNaN(parsed) ? null : Math.round(parsed * 10000) / 100;
}

export function percentToRatio(percent: number | null | undefined): string | null {
  if (percent === null || percent === undefined || Number.isNaN(percent)) {
    return null;
  }
  return (percent / 100).toFixed(4);
}

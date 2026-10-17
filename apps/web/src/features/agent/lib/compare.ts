import type { PlanVersion } from '../api/types';

export function formatAmount(value: string | number | null | undefined, digits = 2): string {
  if (value == null || value === '' || !Number.isFinite(Number(value))) return '—';
  return Number(value).toLocaleString('zh-CN', {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

export function comparePlans(current: PlanVersion, previous: PlanVersion) {
  const before = new Set(previous.result.dishes.map((dish) => dish.dish_id));
  const after = new Set(current.result.dishes.map((dish) => dish.dish_id));
  return {
    added: current.result.dishes.filter((dish) => !before.has(dish.dish_id)),
    removed: previous.result.dishes.filter((dish) => !after.has(dish.dish_id)),
    costDelta:
      current.result.total_cost != null &&
      previous.result.total_cost != null &&
      !current.result.missing_price_warning &&
      !previous.result.missing_price_warning &&
      [...current.result.requirements, ...previous.result.requirements].every(
        (row) => row.unit_price != null && row.estimated_cost != null,
      )
        ? Number(current.result.total_cost) - Number(previous.result.total_cost)
        : null,
    dinerDelta: current.result.diner_count - previous.result.diner_count,
    sameScope:
      current.result.date === previous.result.date &&
      current.result.meal_type === previous.result.meal_type,
  };
}

export const MEAL_OPTIONS = [
  { value: 'BREAKFAST', label: '早餐' },
  { value: 'LUNCH', label: '午餐' },
  { value: 'DINNER', label: '晚餐' },
] as const;

export type DisplayMeal = (typeof MEAL_OPTIONS)[number]['value'];

export function parseDisplayMeal(value: string | null | undefined): DisplayMeal | null {
  if (value === 'BREAKFAST' || value === 'LUNCH' || value === 'DINNER') return value;
  return null;
}

export function defaultMealForTime(date = new Date()): DisplayMeal {
  const hour = date.getHours();
  if (hour < 10) return 'BREAKFAST';
  if (hour < 15) return 'LUNCH';
  return 'DINNER';
}

export function mealLabel(meal: DisplayMeal): string {
  return MEAL_OPTIONS.find((option) => option.value === meal)?.label ?? '当前餐次';
}

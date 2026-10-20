import { describe, expect, it } from 'vitest';
import { defaultMealForTime, mealLabel, parseDisplayMeal } from './meal';

describe('public display meal selection', () => {
  it('parses only supported meal values', () => {
    expect(parseDisplayMeal('BREAKFAST')).toBe('BREAKFAST');
    expect(parseDisplayMeal('LUNCH')).toBe('LUNCH');
    expect(parseDisplayMeal('DINNER')).toBe('DINNER');
    expect(parseDisplayMeal('BRUNCH')).toBeNull();
    expect(parseDisplayMeal(null)).toBeNull();
  });

  it('uses the canteen time windows for the initial meal', () => {
    expect(defaultMealForTime(new Date(2026, 9, 20, 7, 30))).toBe('BREAKFAST');
    expect(defaultMealForTime(new Date(2026, 9, 20, 12, 0))).toBe('LUNCH');
    expect(defaultMealForTime(new Date(2026, 9, 20, 18, 0))).toBe('DINNER');
  });

  it('returns the Chinese label used by the header', () => {
    expect(mealLabel('BREAKFAST')).toBe('早餐');
    expect(mealLabel('LUNCH')).toBe('午餐');
    expect(mealLabel('DINNER')).toBe('晚餐');
  });
});

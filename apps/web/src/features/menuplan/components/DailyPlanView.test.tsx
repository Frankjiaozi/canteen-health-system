import { App } from 'antd';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import type { DailyMenuPlanResponse } from '../types';
import { DailyPlanView } from './DailyPlanView';

function meal(mealType: string, label: string) {
  return {
    meal_type: mealType,
    meal_type_label: label,
    diner_count: 900,
    suggestion_id: `${mealType}-suggestion`,
    total_cost: '100',
    budget: '7200',
    dishes: [
      {
        dish_id: `${mealType}-dish`,
        dish_name: `${label}菜`,
        planned_servings: '500',
        predicted_servings: '500',
      },
    ],
    gaps: [],
    reasons: [],
    requirements: [],
  };
}

const plan = {
  date: '2026-10-20',
  meals: [meal('BREAKFAST', '早餐'), meal('LUNCH', '午餐'), meal('DINNER', '晚餐')],
  requirements: [],
  total_cost: '300',
  budget: '21600',
  servings_note: '三餐合并采购',
  fallback_dishes: [],
  notes: ['早餐固定组合'],
  suggestion_ids: {},
  calculation_version: 'test',
} as unknown as DailyMenuPlanResponse;

beforeEach(() => {
  vi.stubGlobal('matchMedia', () => ({ matches: false }));
});

it('三餐一次展示，并在结果区直接提供同步按钮', () => {
  const onSync = vi.fn();
  render(
    <App>
      <DailyPlanView plan={plan} canWrite syncing={false} outcomes={null} onSync={onSync} />
    </App>,
  );

  expect(screen.getByText(/早餐 · 900 人次/)).toBeInTheDocument();
  expect(screen.getByText(/午餐 · 900 人次/)).toBeInTheDocument();
  expect(screen.getByText(/晚餐 · 900 人次/)).toBeInTheDocument();
  expect(screen.getByText(/全天食材采购建议/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '同步三餐至当日数据' }));
  expect(onSync).toHaveBeenCalledOnce();
});

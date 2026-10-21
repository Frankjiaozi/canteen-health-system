import { render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { useMenuOverview } from '../hooks/useDashboard';
import type { MenuOverviewResponse } from '../types';
import { MenuOverview } from './MenuOverview';

vi.mock('../hooks/useDashboard', () => ({
  useMenuOverview: vi.fn(),
}));

const overview: MenuOverviewResponse = {
  today: '2026-10-19',
  tomorrow: '2026-10-20',
  days: [
    {
      date: '2026-10-19',
      day_label: '今天',
      meals: [
        {
          meal_type: 'BREAKFAST',
          meal_type_label: '早餐',
          status: 'ACTUAL',
          status_label: '实际供应',
          diner_count: 620,
          dishes: [
            {
              dish_id: 'breakfast-dish',
              name: '鲜肉包',
              is_shared: false,
              category_label: '主食',
              cooking_method_label: '蒸',
              planned_servings: '620',
            },
          ],
        },
        {
          meal_type: 'LUNCH',
          meal_type_label: '午餐',
          status: 'ACTUAL',
          status_label: '实际供应',
          diner_count: 920,
          dishes: [],
        },
        {
          meal_type: 'DINNER',
          meal_type_label: '晚餐',
          status: 'ACTUAL',
          status_label: '实际供应',
          diner_count: 780,
          dishes: [],
        },
      ],
    },
    {
      date: '2026-10-20',
      day_label: '明天',
      meals: [
        {
          meal_type: 'BREAKFAST',
          meal_type_label: '早餐',
          status: 'NOT_PLANNED',
          status_label: '未安排',
          diner_count: null,
          dishes: [],
        },
        {
          meal_type: 'LUNCH',
          meal_type_label: '午餐',
          status: 'PLANNED',
          status_label: '计划供应',
          diner_count: null,
          dishes: [
            {
              dish_id: 'lunch-dish',
              name: '清炒西兰花',
              package_codes: ['A'],
              package_labels: ['套餐 A'],
              is_shared: false,
              category_label: '素菜',
              cooking_method_label: '清炒',
              planned_servings: '830',
            },
          ],
        },
        {
          meal_type: 'DINNER',
          meal_type_label: '晚餐',
          status: 'NOT_PLANNED',
          status_label: '未安排',
          diner_count: null,
          dishes: [],
        },
      ],
    },
  ],
};

beforeEach(() => {
  vi.stubGlobal('matchMedia', () => ({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
  vi.mocked(useMenuOverview).mockReturnValue({
    data: overview,
    isPending: false,
    isError: false,
  } as unknown as ReturnType<typeof useMenuOverview>);
});

it('按今天和明天展示三餐，并区分实际、计划与未安排', () => {
  render(<MenuOverview />);

  expect(screen.getByText('今天 · 2026-10-19')).toBeInTheDocument();
  expect(screen.getByText('明天 · 2026-10-20')).toBeInTheDocument();
  expect(screen.getAllByText('早餐')).toHaveLength(2);
  expect(screen.getAllByText('午餐')).toHaveLength(2);
  expect(screen.getAllByText('晚餐')).toHaveLength(2);

  expect(screen.getByText('鲜肉包')).toBeInTheDocument();
  expect(screen.getByText('620 人次')).toBeInTheDocument();
  expect(screen.getByText('清炒西兰花')).toBeInTheDocument();
  expect(screen.getByText('套餐 A')).toBeInTheDocument();
  expect(screen.getByText(/830 份/)).toBeInTheDocument();
  expect(screen.getAllByText('实际供应')).toHaveLength(3);
  expect(screen.getAllByText('计划供应')).toHaveLength(1);
  expect(screen.getAllByText('未安排')).toHaveLength(4);
  expect(screen.getAllByText('暂无菜品')).toHaveLength(2);
});

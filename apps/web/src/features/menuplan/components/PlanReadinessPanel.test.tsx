import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import { fetchPlanReadiness } from '../api/menuPlanApi';
import type { PlanReadiness } from '../types';
import { PlanReadinessPanel } from './PlanReadinessPanel';

vi.mock('../api/menuPlanApi', () => ({ fetchPlanReadiness: vi.fn() }));
vi.mock('@/shared/hooks/useMenuDataRevision', () => ({ useMenuDataRevision: () => 0 }));
const report: PlanReadiness = {
  on_date: '2026-10-23',
  checked_at: '2026-10-22T01:00:00Z',
  meal_type: 'BREAKFAST',
  meal_type_label: '早餐',
  state: 'blocked',
  active_dish_count: 40,
  candidate_count: 0,
  available_count: 0,
  excluded_count: 0,
  predicted_count: 0,
  history_start: '2026-08-28',
  history_end: '2026-10-22',
  history_record_count: 0,
  days_with_records: 0,
  latest_record_date: null,
  latest_diner_count: null,
  missing_price_count: 0,
  missing_nutrition_count: 0,
  categories: [],
  issues: [
    {
      code: 'breakfast',
      severity: 'blocking',
      title: '早餐菜品未配置',
      detail: '请完善固定供应菜品。',
      action: '核对菜品与配方。',
      link: '/admin/dishes',
    },
  ],
  issue_count: 1,
  truncated: false,
  note: '结构检查不保证求解成功。',
};
function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}
beforeEach(() => {
  vi.mocked(fetchPlanReadiness).mockReset();
  vi.mocked(fetchPlanReadiness).mockImplementation(async (date, meal) => ({
    ...report,
    on_date: date,
    meal_type: meal,
  }));
  vi.stubGlobal('matchMedia', () => ({ matches: false }));
});

it('按所选日期检查三餐，展开问题可前往原数据', async () => {
  render(<PlanReadinessPanel onDate="2026-10-23" />, { wrapper });
  expect(await screen.findAllByText('需要补齐数据')).toHaveLength(3);
  expect(fetchPlanReadiness).toHaveBeenCalledTimes(3);
  for (const meal of ['BREAKFAST', 'LUNCH', 'DINNER'])
    expect(fetchPlanReadiness).toHaveBeenCalledWith('2026-10-23', meal, expect.any(AbortSignal));
  fireEvent.click(screen.getAllByText('查看 1 项待办与依据')[0]);
  expect(await screen.findByRole('link', { name: '前往核对' })).toHaveAttribute(
    'href',
    '/admin/dishes',
  );
});

it('切换日期餐次后重新检查，不显示上一餐结果', async () => {
  const view = render(<PlanReadinessPanel onDate="2026-10-23" mealType="BREAKFAST" />, { wrapper });
  await screen.findByText('需要补齐数据');
  vi.mocked(fetchPlanReadiness).mockResolvedValue({
    ...report,
    on_date: '2026-10-24',
    meal_type: 'LUNCH',
    state: 'ready',
    issues: [],
    issue_count: 0,
  });
  view.rerender(<PlanReadinessPanel onDate="2026-10-24" mealType="LUNCH" />);
  await screen.findByText('未见数据缺口');
  expect(screen.queryByText('需要补齐数据')).not.toBeInTheDocument();
  expect(fetchPlanReadiness).toHaveBeenLastCalledWith(
    '2026-10-24',
    'LUNCH',
    expect.any(AbortSignal),
  );
});

it('接口失败不会显示为数据齐全，允许重新检查', async () => {
  vi.mocked(fetchPlanReadiness).mockRejectedValueOnce(new Error('offline'));
  render(<PlanReadinessPanel onDate="2026-10-23" mealType="BREAKFAST" />, { wrapper });
  await screen.findByText('本次检查未完成');
  expect(screen.queryByText('未见数据缺口')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '重新检查' }));
  await waitFor(() => expect(screen.queryByText('本次检查未完成')).not.toBeInTheDocument());
  expect(await screen.findByText('需要补齐数据')).toBeInTheDocument();
});

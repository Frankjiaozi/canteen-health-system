import { expect, test } from '@playwright/test';
import { loginAs } from './helpers';

// 拦截生成请求，不向演示台账写方案；检查用户切换条件后的页面行为。
test('生成三餐后切换日期，旧方案不再显示或允许同步', async ({ page }) => {
  await loginAs(page, 'recorder');
  await page.route('**/api/v1/menu-plan/generate-day*', (route) =>
    route.fulfill({
      json: {
        date: '2026-10-21',
        meals: [
          {
            meal_type: 'LUNCH',
            meal_type_label: '午餐',
            diner_count: 100,
            suggestion_id: 'test-plan',
            total_cost: '100',
            budget: '800',
            dishes: [],
            gaps: [],
            reasons: [],
            requirements: [],
          },
        ],
        requirements: [],
        total_cost: '100',
        budget: '800',
        fallback_dishes: [],
        notes: [],
        suggestion_ids: {},
        calculation_version: 'test',
      },
    }),
  );
  await page.goto('/admin/menu-plan?date=2026-10-21');
  await page.getByRole('button', { name: '生成三餐' }).click();
  await expect(page.getByText('① 三餐安排 · 2026-10-21')).toBeVisible();
  await page.getByRole('textbox', { name: /日期/ }).fill('2026-10-22');
  await page.getByRole('textbox', { name: /日期/ }).press('Enter');
  await expect(page).toHaveURL(/date=2026-10-22/);
  await expect(page.getByText('① 三餐安排 · 2026-10-21')).toHaveCount(0);
  await expect(page.getByRole('button', { name: '同步三餐至当日数据' })).toHaveCount(0);
});

test('批量生成后切换餐次，旧结果及导入入口清空', async ({ page }) => {
  await loginAs(page, 'recorder');
  await page.route('**/api/v1/menu-plan/batch/generate*', (route) =>
    route.fulfill({
      json: {
        rows: [
          {
            date: '2026-10-21',
            status: 'GENERATED',
            status_label: '已生成',
            suggestion_id: 'test-plan',
            dish_names: ['测试午餐'],
          },
        ],
        message: '生成完成',
      },
    }),
  );
  await page.goto('/admin/menu-plan');
  await page.getByText('批量排菜单', { exact: true }).first().click();
  await page.getByRole('button', { name: '批量生成', exact: true }).click();
  await expect(page.getByText('测试午餐')).toBeVisible();
  await page.getByText('晚餐', { exact: true }).click();
  await expect(page.getByText('测试午餐')).toHaveCount(0);
  await expect(page.getByRole('button', { name: '采纳并同步' })).toHaveCount(0);
});

import { expect, test } from '@playwright/test';
import { loginAs } from './helpers';

test('注册关闭时隐藏入口，直接访问注册页也不会显示提交表单', async ({ page }) => {
  await page.route('**/api/v1/auth/options', (route) =>
    route.fulfill({ json: { registration_enabled: false } }),
  );
  await page.goto('/login');
  await expect(page.getByText('需要账号？请联系管理员开通。')).toBeVisible();
  await expect(page.getByRole('link', { name: '立即注册' })).toHaveCount(0);
  await page.goto('/register');
  await expect(page.getByText('自助注册已关闭')).toBeVisible();
  await expect(page.locator('form')).toHaveCount(0);
});

test('采集单未保存时切换页面可取消或明确放弃', async ({ page }) => {
  await loginAs(page, 'recorder');
  await page.goto('/admin/collection');
  await page.getByLabel('就餐人次').fill('123');
  await page.getByRole('menuitem', { name: /食材库/ }).click();
  await expect(page.getByRole('dialog', { name: '采集单尚未保存' })).toBeVisible();
  await page.getByRole('button', { name: '继续填写' }).click();
  await expect(page).toHaveURL(/\/admin\/collection$/);
  await expect(page.getByLabel('就餐人次')).toHaveValue('123');
  await page.getByRole('menuitem', { name: /食材库/ }).click();
  await page.getByRole('button', { name: '放弃修改' }).click();
  await expect(page).toHaveURL(/\/admin\/ingredients$/);
});

test('学校账号可读历史采购快照，刷新后可再次读取', async ({ page }) => {
  await loginAs(page, 'school');
  await page.route('**/api/v1/menu-plan/history*', (route) =>
    route.fulfill({
      json: [
        {
          created_at: '2026-10-20T10:00:00+08:00',
          status_label: '已发布',
          plan: {
            suggestion_id: 'saved-plan',
            date: '2026-10-21',
            meal_type: 'LUNCH',
            meal_type_label: '午餐',
            dishes: [{ dish_id: 'saved-dish', dish_name: '历史清蒸鱼', planned_servings: '100' }],
            requirements: [
              {
                name: '鲈鱼',
                quantity: '12',
                unit: '公斤',
                unit_price: '20',
                estimated_cost: '240',
              },
            ],
            total_cost: '240',
            budget: '800',
            servings_note: '保存时的计算结果',
          },
        },
      ],
    }),
  );
  for (let index = 0; index < 2; index += 1) {
    await page.goto('/admin/menu-plan?date=2026-10-21');
    await page.getByRole('button', { name: /2026-10-21 · 午餐/ }).click();
    await expect(page.getByText('历史清蒸鱼')).toBeVisible();
    await expect(page.getByRole('cell', { name: '鲈鱼', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: '生成三餐' })).toHaveCount(0);
  }
});

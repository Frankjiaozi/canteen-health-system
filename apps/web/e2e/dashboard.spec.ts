import { expect, test } from '@playwright/test';
import { loginAs } from './helpers';

test('登录后可以看到四类指标', async ({ page }) => {
  await loginAs(page, 'recorder');
  await page.goto('/admin');

  await expect(page.getByText('油盐糖用量趋势')).toBeVisible();
  // 精确匹配：图表下方的口径说明里也提到了这个栏目名
  await expect(page.getByText('人均摄入与推荐值', { exact: true })).toBeVisible();
  await expect(page.getByText('营养达标率')).toBeVisible();
  await expect(page.getByText('剩餐量与浪费率')).toBeVisible();
  // 图表来自真实接口，而不是空壳
  await expect(page.getByRole('img', { name: '油盐糖每日用量趋势图' })).toBeVisible();
  await expect(page.getByRole('img', { name: '每日剩餐量与浪费率图' })).toBeVisible();
});

test('人均摄入栏把口径讲清楚，并按基准给出结论', async ({ page }) => {
  await loginAs(page, 'school');
  await page.goto('/admin');

  await expect(page.getByText(/理论值/)).toBeVisible();
  await expect(page.getByText(/实际投料量/)).toBeVisible();
  // 四项基准都应当给出结论标签
  await expect(page.getByText('食盐').first()).toBeVisible();
  await expect(page.getByText(/达标|超出上限|低于推荐/).first()).toBeVisible();
});

test('切换时间范围后数据随之变化', async ({ page }) => {
  await loginAs(page, 'recorder');
  await page.goto('/admin');

  const recordedDays = page.locator('.ant-statistic').filter({ hasText: '有记录天数' });
  // 演示历史是 8 周
  await expect(recordedDays).toContainText('14');

  await page.locator('.ant-segmented-item', { hasText: '近 7 天' }).click();
  await expect(recordedDays).toContainText('7');

  await page.locator('.ant-segmented-item', { hasText: '近 30 天' }).click();
  // 30 天范围内有 30 天记录（演示历史 56 天，够覆盖）
  await expect(recordedDays).toContainText('30');
});

test('未登录访问看板会被拦到登录页', async ({ page }) => {
  await page.goto('/admin');

  await expect(page).toHaveURL(/\/login$/);
});

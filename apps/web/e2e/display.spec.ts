import { expect, test } from '@playwright/test';

test('公开大屏不需要登录就能看到今日菜单与营养', async ({ page }) => {
  await page.goto('/display');

  await expect(page.getByText('今日菜单与营养')).toBeVisible();
  await expect(page.getByText('知味 · 校园智慧膳食平台')).toBeVisible();
  // 免登录：不应被重定向到登录页
  await expect(page).not.toHaveURL(/login/);

  // 菜品与营养指标来自真实的营养计算结果
  await expect(page.getByText('米饭')).toBeVisible();
  await expect(page.getByText('能量').first()).toBeVisible();
  await expect(page.getByText('276.80').first()).toBeVisible();
});

test('公开大屏展示膳食指南对照条与合规说明', async ({ page }) => {
  await page.goto('/display');

  await expect(page.getByText('食盐').first()).toBeVisible();
  await expect(page.getByText('烹调油').first()).toBeVisible();
  await expect(page.getByText('添加糖').first()).toBeVisible();
  await expect(page.getByText(/中国居民膳食指南/).first()).toBeVisible();
  await expect(page.getByText(/不针对任何个人/)).toBeVisible();
});

for (const viewport of [
  { name: '1920 大屏', width: 1920, height: 1080 },
  { name: '1366 笔记本', width: 1366, height: 768 },
  { name: '390 手机竖屏', width: 390, height: 844 },
]) {
  test(`公开大屏在${viewport.name}下不溢出`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.goto('/display');
    await expect(page.getByText('今日菜单与营养')).toBeVisible();

    const overflow = await page.evaluate(() => ({
      horizontal: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      vertical: document.documentElement.scrollHeight - document.documentElement.clientHeight,
    }));

    expect(overflow.horizontal).toBeLessThanOrEqual(0);
    expect(overflow.vertical).toBeLessThanOrEqual(0);
  });
}

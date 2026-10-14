import { randomUUID } from 'node:crypto';
import { expect, test } from '@playwright/test';

const password = 'SignupTest2026';

test('注册、刷新、退出并重新登录，保留原访问目标', async ({ page }) => {
  const username = `e2e_signup_${randomUUID().replaceAll('-', '').slice(0, 12)}`;
  await page.goto('/admin/ingredients');
  await expect(page).toHaveURL(/\/login$/);
  await page.getByRole('link', { name: '立即注册' }).click();
  await expect(page).toHaveURL(/\/register$/);
  await page.getByLabel('显示名称', { exact: true }).fill('注册流程测试');
  await page.getByLabel('登录名', { exact: true }).fill(username);
  await page.getByLabel('密码', { exact: true }).fill(password);
  await page.getByLabel('确认密码', { exact: true }).fill('Different2026');
  await page.getByRole('button', { name: '注册并登录' }).click();
  await expect(page.getByText('两次输入的密码不一致')).toBeVisible();
  await page.getByLabel('确认密码', { exact: true }).fill(password);
  await page.getByRole('button', { name: '注册并登录' }).click();
  await expect(page).toHaveURL(/\/admin\/ingredients$/);
  await expect(page.getByText('注册流程测试')).toBeVisible();
  await expect(page.getByText('食堂录入员', { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText('注册流程测试')).toBeVisible();
  await page.getByRole('button', { name: '退出' }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto('/admin');
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel('登录名').fill(username.toUpperCase());
  await page.getByLabel('口令').fill(password);
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await expect(page).toHaveURL(/\/admin$/);
  await expect(page.getByText('油盐糖用量趋势')).toBeVisible();
  await expect(page.getByText('注册流程测试').first()).toBeVisible();
});

test('用户名冲突显示提示且不切换登录状态', async ({ page }) => {
  await page.goto('/register');
  await page.getByLabel('显示名称', { exact: true }).fill('重名测试');
  await page.getByLabel('登录名', { exact: true }).fill('recorder');
  await page.getByLabel('密码', { exact: true }).fill(password);
  await page.getByLabel('确认密码', { exact: true }).fill(password);
  await page.getByRole('button', { name: '注册并登录' }).click();
  await expect(page.getByText('该登录名已被使用，请换一个')).toBeVisible();
  await expect(page).toHaveURL(/\/register$/);
  await page.getByRole('link', { name: '返回登录' }).click();
  await expect(page).toHaveURL(/\/login$/);
});

test('退出接口失败时保留当前账号并显示错误', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('登录名').fill('canteen');
  await page.getByLabel('口令').fill('canteen@2026');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await expect(page).toHaveURL(/\/admin$/);
  await page.route('**/api/v1/auth/logout', async (route) => {
    await route.fulfill({
      status: 503,
      json: { code: 'service_unavailable', message: '退出暂时不可用', details: null },
    });
  });
  await page.getByRole('button', { name: '退出' }).click();
  await expect(page.getByText('退出暂时不可用')).toBeVisible();
  await expect(page).toHaveURL(/\/admin$/);
  await expect(page.getByText('油盐糖用量趋势')).toBeVisible();
});

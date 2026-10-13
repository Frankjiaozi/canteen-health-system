import { expect, test } from '@playwright/test';

const DEMO_PASSWORD = 'canteen@2026';

// 系统内没有学生端，登录页只服务三类管理角色
async function login(page: import('@playwright/test').Page, username: string) {
  await page.goto('/login');
  await page.getByLabel('登录名').fill(username);
  await page.getByLabel('口令').fill(DEMO_PASSWORD);
  await page.getByRole('button', { name: '登录' }).click();
}

test('未登录访问管理端会跳转到登录页', async ({ page }) => {
  await page.goto('/admin/ingredients');

  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole('button', { name: '登录' })).toBeVisible();
});

test('口令错误时留在登录页并给出提示', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('登录名').fill('recorder');
  await page.getByLabel('口令').fill('definitely-wrong');
  await page.getByRole('button', { name: '登录' }).click();

  await expect(page.getByText('用户名或密码不正确')).toBeVisible();
  await expect(page).toHaveURL(/\/login$/);
});

test('登录成功后进入管理端并展示角色', async ({ page }) => {
  await login(page, 'recorder');

  await expect(page).toHaveURL(/\/admin$/);
  await expect(page.getByRole('heading', { name: /欢迎回来/ })).toBeVisible();
  await expect(page.getByText('食堂录入员').first()).toBeVisible();
});

test('刷新页面后登录态保持', async ({ page }) => {
  await login(page, 'canteen');
  await expect(page).toHaveURL(/\/admin$/);

  await page.reload();

  await expect(page).toHaveURL(/\/admin$/);
  await expect(page.getByText('食堂管理员').first()).toBeVisible();
});

test('退出登录后回到登录页且再访问管理端仍被拦截', async ({ page }) => {
  await login(page, 'recorder');
  await expect(page).toHaveURL(/\/admin$/);

  await page.getByRole('button', { name: '退出' }).click();
  await expect(page).toHaveURL(/\/login$/);

  await page.goto('/admin');
  await expect(page).toHaveURL(/\/login$/);
});

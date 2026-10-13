import { expect, type Page } from '@playwright/test';

export const DEMO_PASSWORD = 'canteen@2026';

/** 以演示账号登录并等到管理端首屏就绪。 */
export async function loginAs(page: Page, username: string) {
  await page.goto('/login');
  await page.getByLabel('登录名').fill(username);
  await page.getByLabel('口令').fill(DEMO_PASSWORD);
  await page.getByRole('button', { name: '登录' }).click();
  await expect(page).toHaveURL(/\/admin$/);
}

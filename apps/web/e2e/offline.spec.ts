import { expect, test } from '@playwright/test';
import { loginAs } from './helpers';

test('断网时给出明确提示，恢复后提示消失', async ({ page, context }) => {
  await loginAs(page, 'recorder');
  await page.goto('/admin/ingredients');

  // 联网时不显示提示条
  await expect(page.getByText('网络已断开')).toHaveCount(0);

  await context.setOffline(true);
  await expect(page.getByText('网络已断开')).toBeVisible();
  // 如实说明两件事：采集页的录入不会丢（会进本地队列），其他页面的修改确实提交不了
  await expect(page.getByText(/采集页可以继续录入/)).toBeVisible();
  await expect(page.getByText(/其他页面的修改暂时提交不了/)).toBeVisible();

  await context.setOffline(false);
  await expect(page.getByText('网络已断开')).toHaveCount(0);
});

test('PWA 清单可被浏览器获取', async ({ request }) => {
  const response = await request.get('/manifest.webmanifest');

  expect(response.status()).toBe(200);
  const manifest = await response.json();
  expect(manifest.name).toBe('知味 · 校园智慧膳食平台');
  expect(manifest.lang).toBe('zh-CN');
  expect(manifest.icons.length).toBeGreaterThan(0);
});

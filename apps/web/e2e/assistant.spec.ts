import { expect, test } from '@playwright/test';
import { loginAs } from './helpers';

/**
 * AI 助手抽屉（阶段一：只读问答）。
 *
 * 这里**不测真模型**：CI 与本地开发都不一定有模型端点，而助手在没接模型时必须
 * 如实说「未接模型」——那本身就是一条要守住的行为（界面不能给一个点了没反应的输入框）。
 * 所以这条用例验的是「界面与接口说的一致」，两种配置下都成立。
 */
test('助手抽屉打开后的状态与接口说的一致', async ({ page }) => {
  await loginAs(page, 'recorder');

  const status = await (await page.request.get('/api/v1/assistant/status')).json();
  expect(status.tools.length).toBeGreaterThanOrEqual(5);
  expect(status.tools.every((tool: { read_only: boolean }) => tool.read_only)).toBe(true);

  await page.getByRole('button', { name: 'AI 助手' }).click();

  const drawer = page.getByRole('dialog');
  await expect(drawer).toBeVisible();
  await expect(drawer.getByText('AI 助手')).toBeVisible();

  const input = drawer.getByPlaceholder(/最近两周盐用超了吗|助手未接模型/);
  if (status.enabled) {
    await expect(drawer.getByText(/已接模型/)).toBeVisible();
    await expect(input).toBeEnabled();
  } else {
    await expect(drawer.getByText('未接模型')).toBeVisible();
    await expect(drawer.getByText(/ASSISTANT_BASE_URL/)).toBeVisible();
    await expect(input).toBeDisabled();
  }
});

test('未登录看不到助手状态', async ({ page }) => {
  const response = await page.request.get('/api/v1/assistant/status');
  expect(response.status()).toBe(401);
});

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
  // 历史对话是审计入口，不接模型也要在（否则「助手做过什么」就查不到了）
  await expect(drawer.getByRole('button', { name: /历史对话/ })).toBeVisible();
  await expect(drawer.getByRole('button', { name: '新对话' })).toBeVisible();

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

test('接了模型时：边查边回，工具痕迹与文字都进对话', async ({ page }) => {
  // 先登录再问状态：未登录时状态接口返回 401，`enabled` 读出来是 undefined，
  // 那样会把「没配模型」和「没登录」混成一回事，用例永远被跳过
  await loginAs(page, 'recorder');
  const status = await (await page.request.get('/api/v1/assistant/status')).json();
  // CI 与没配模型的环境没有模型端点，这条跳过；配了模型的机器上才真跑
  test.skip(!status.enabled, '没有配置模型端点，跳过真实对话');
  test.setTimeout(180_000);

  await page.getByRole('button', { name: 'AI 助手' }).click();
  const drawer = page.getByRole('dialog');
  await expect(drawer).toBeVisible();

  await drawer.getByPlaceholder(/最近两周盐用超了吗/).fill('今天午餐供应哪些菜？');
  await drawer.getByRole('button', { name: '问' }).click();

  // 先出工具痕迹（说明过程是边跑边显示的），再出文字
  await expect(drawer.getByText(/查某天的菜单|菜品/).first()).toBeVisible({ timeout: 120_000 });
  await expect(drawer.getByText(/午餐|供应/).first()).toBeVisible({ timeout: 120_000 });

  // 回答与对话都落了库：刷新抽屉（历史对话）还能读到这次问答
  await drawer.getByRole('button', { name: /历史对话/ }).click();
  await expect(drawer.getByText(/条消息/).first()).toBeVisible({ timeout: 30_000 });
});

import { expect, test } from '@playwright/test';
import { loginAs } from './helpers';

test('登录后可以看到四类指标', async ({ page }) => {
  await loginAs(page, 'recorder');
  await page.goto('/admin');
  await page.getByRole('tab', { name: '营养分析' }).click();
  const panel = page.getByRole('tabpanel', { name: '营养分析' });

  await expect(panel.getByText('油盐糖用量趋势', { exact: true })).toBeVisible();
  // 精确匹配：图表下方的口径说明里也提到了这个栏目名
  await expect(panel.getByText('人均摄入与推荐值', { exact: true })).toBeVisible();
  await expect(panel.getByText('营养达标率', { exact: true })).toBeVisible();
  await expect(panel.getByText('剩餐量与浪费率', { exact: true })).toBeVisible();
  // 图表来自真实接口，而不是空壳
  await expect(page.getByRole('img', { name: '油盐糖每日用量趋势图' })).toBeVisible();
  await expect(page.getByRole('img', { name: '每日剩餐量与浪费率图' })).toBeVisible();
});

test('人均摄入栏把口径讲清楚，并按基准给出结论', async ({ page }) => {
  await loginAs(page, 'school');
  await page.goto('/admin');
  await page.getByRole('tab', { name: '营养分析' }).click();
  const panel = page.getByRole('tabpanel', { name: '营养分析' });

  await panel.getByText('查看来源与核算口径', { exact: true }).hover();
  const popover = page.locator('.ant-popover:not(.ant-popover-hidden)');
  await expect(popover).toContainText(/配方理论值/);
  await expect(popover).toContainText(/实际投料量/);
  // 四项基准都应当给出结论标签
  await expect(panel.getByText('食盐', { exact: true }).first()).toBeVisible();
  await expect(panel.getByText(/达标|超出上限|低于推荐/).first()).toBeVisible();
});

test('切换时间范围后数据随之变化', async ({ page }) => {
  await loginAs(page, 'recorder');
  await page.goto('/admin');
  await page.getByRole('tab', { name: '营养分析' }).click();
  const panel = page.getByRole('tabpanel', { name: '营养分析' });

  const recordedDays = panel.locator('.zw-metric').filter({ hasText: '有记录天数' });
  // 演示历史是 8 周
  await expect(recordedDays).toContainText('14');

  await panel.locator('.ant-segmented-item', { hasText: '近 7 天' }).click();
  await expect(recordedDays).toContainText('7');

  await panel.locator('.ant-segmented-item', { hasText: '近 30 天' }).click();
  // 30 天范围内有 30 天记录（演示历史 56 天，够覆盖）
  await expect(recordedDays).toContainText('30');
});

test('看板可以切到今明菜单，并按三餐展示', async ({ page }) => {
  await loginAs(page, 'school');
  await page.goto('/admin');

  await page.getByRole('tab', { name: '今明菜单' }).click();
  await expect(page.locator('.zw-menu-day-title').filter({ hasText: '今天' })).toContainText(
    /\d{4}-\d{2}-\d{2}/,
  );
  await expect(page.locator('.zw-menu-day-title').filter({ hasText: '明天' })).toContainText(
    /\d{4}-\d{2}-\d{2}/,
  );
  await expect(
    page.locator('.zw-menu-meal-name h3').filter({ hasText: '早餐' }).first(),
  ).toBeVisible();
  await expect(
    page.locator('.zw-menu-meal-name h3').filter({ hasText: '午餐' }).first(),
  ).toBeVisible();
  await expect(
    page.locator('.zw-menu-meal-name h3').filter({ hasText: '晚餐' }).first(),
  ).toBeVisible();
});

test('未登录访问看板会被拦到登录页', async ({ page }) => {
  await page.goto('/admin');

  await expect(page).toHaveURL(/\/login$/);
});

test('首页按参考图呈现膳食总览和真实指标', async ({ page }) => {
  await loginAs(page, 'recorder');
  await expect(page.getByRole('heading', { name: '今日膳食概览', exact: true })).toBeVisible();
  await expect(page.getByText('油盐糖用量趋势', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: '人均每日参考' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '知食之味， 养日常之美。' })).toHaveCount(0);
  await page.getByRole('button', { name: '推荐几道低盐家常菜', exact: true }).click();
  await expect(page.getByRole('textbox', { name: '向膳食助手提问' })).toHaveValue(
    '推荐几道低盐家常菜',
  );
});

test('近 7、14、30 天保留完整日历，并显示实际记录天数', async ({ page }) => {
  await loginAs(page, 'recorder');
  for (const days of [7, 14, 30]) {
    await page
      .locator('.zw-reference-trend .ant-segmented-item')
      .filter({ hasText: `近 ${days} 天` })
      .click();
    const response = await page.request.get(`/api/v1/dashboard/trends?days=${days}`);
    expect(response.ok()).toBeTruthy();
    const body = await response.json();
    expect(body.points.length).toBeLessThanOrEqual(days);
    expect(
      body.points.every(
        (point: { date: string }) => point.date >= body.start && point.date <= body.end,
      ),
    ).toBe(true);

    const actualDays = body.points.filter(
      (point: { diner_count: number | null }) => point.diner_count !== null,
    ).length;
    await expect(page.locator('.zw-data-note').last()).toContainText(`共 ${days} 天`);
    await expect(page.locator('.zw-data-note').last()).toContainText(`${actualDays} 天有采集记录`);
    await expect(page.locator('.zw-data-note').last()).toContainText(
      `${body.start} 至 ${body.end}`,
    );
  }
});

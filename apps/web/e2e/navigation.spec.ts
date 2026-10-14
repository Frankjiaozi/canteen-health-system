import { expect, test } from '@playwright/test';
import { loginAs } from './helpers';

test('侧边栏按使用动线分成三块', async ({ page }) => {
  await loginAs(page, 'recorder');

  const menu = page.getByRole('menu');
  // 首页是数据看板，且登录后就落在这里
  await expect(menu.getByRole('menuitem', { name: /数据看板/ })).toBeVisible();

  // 两个分组：基础数据（建库）与日常运行（每天每周的活）
  await expect(menu.getByRole('menuitem', { name: /基础数据/ })).toBeVisible();
  await expect(menu.getByRole('menuitem', { name: /日常运行/ })).toBeVisible();
});

test('基础数据分组里是食材、调味料与菜品配方', async ({ page }) => {
  await loginAs(page, 'recorder');
  await page.getByRole('menuitem', { name: /基础数据/ }).click();

  for (const name of ['食材库', '调味料库', '菜品与配方']) {
    await expect(page.getByRole('menuitem', { name })).toBeVisible();
  }
});

test('日常运行分组按时间顺序排，点进去能到对应页面', async ({ page }) => {
  await loginAs(page, 'recorder');
  await page.getByRole('menuitem', { name: /日常运行/ }).click();

  // 「菜单推荐」与「采购预测」已合成「明日菜单与采购」，四项变三项
  for (const name of ['明日菜单与采购', '每日采集', '抽样纠偏']) {
    await expect(page.getByRole('menuitem', { name })).toBeVisible();
  }
  await expect(page.getByRole('menuitem', { name: '采购预测' })).toHaveCount(0);

  await page.getByRole('menuitem', { name: '每日采集' }).click();
  await expect(page).toHaveURL(/\/admin\/collection$/);
});

test('旧的菜单推荐与采购预测地址跳到合并后的页面', async ({ page }) => {
  await loginAs(page, 'recorder');

  await page.goto('/admin/recommendation');
  await expect(page).toHaveURL(/\/admin\/menu-plan$/);

  await page.goto('/admin/forecast');
  await expect(page).toHaveURL(/\/admin\/menu-plan$/);
  await expect(page.getByText('明日菜单与采购', { exact: true })).toBeVisible();
});

test('当前页面所在的分组会自动展开', async ({ page }) => {
  await loginAs(page, 'recorder');

  // 直接打开一个分组里的页面，该分组应当已经展开，否则看不出自己在哪
  await page.goto('/admin/calibration');

  await expect(page.getByRole('menuitem', { name: '抽样纠偏' })).toBeVisible();
  await expect(page).toHaveURL(/\/admin\/calibration$/);
});

test('旧的看板地址仍然可用，跳回首页', async ({ page }) => {
  await loginAs(page, 'recorder');

  await page.goto('/admin/dashboard');

  await expect(page).toHaveURL(/\/admin$/);
  await expect(page.getByText('油盐糖用量趋势')).toBeVisible();
});

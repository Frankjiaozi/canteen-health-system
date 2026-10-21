import { expect, test } from '@playwright/test';
import { loginAs } from './helpers';

test('切换业务页面后目录顺序、宽度与品牌位置保持一致', async ({ page }) => {
  await loginAs(page, 'recorder');
  const menu = page.locator('.zw-admin-menu');
  const labels = ['总览', '膳食助手', '菜品与配方', '食材库', '菜单与采购', '每日采集'];
  const routes = [
    '/admin',
    '/admin/agent',
    '/admin/dishes',
    '/admin/ingredients',
    '/admin/menu-plan',
    '/admin/collection',
  ];
  const initialBrand = await page.locator('.zw-admin-brand').boundingBox();
  for (let index = 0; index < routes.length; index += 1) {
    await menu.getByRole('menuitem', { name: new RegExp(labels[index]) }).click();
    await expect(page).toHaveURL(new RegExp(`${routes[index]}$`));
    await expect(menu.locator(':scope > .ant-menu-item')).toHaveText(labels);
    await expect(menu.locator('.ant-menu-item-selected')).toContainText(labels[index]);
    expect((await page.locator('.zw-admin-sider').boundingBox())?.width).toBe(178);
    expect(await page.locator('.zw-admin-brand').boundingBox()).toEqual(initialBrand);
  }
});

test('更多工具展开状态在页面切换与前进后退时保留', async ({ page }) => {
  await loginAs(page, 'recorder');
  const menu = page.locator('.zw-admin-menu');
  await menu.getByRole('menuitem', { name: /更多工具/ }).click();
  await menu.getByRole('menuitem', { name: '调味料库', exact: true }).click();
  await expect(page).toHaveURL(/\/admin\/seasonings$/);
  await menu.getByRole('menuitem', { name: '抽样纠偏', exact: true }).click();
  await expect(page).toHaveURL(/\/admin\/calibration$/);
  await menu.getByRole('menuitem', { name: /总览/ }).click();
  await expect(menu.getByRole('menuitem', { name: '抽样纠偏', exact: true })).toBeVisible();
  await page.goBack();
  await expect(menu.locator('.ant-menu-item-selected')).toHaveText('抽样纠偏');
  await page.goForward();
  await expect(menu.locator('.ant-menu-item-selected')).toHaveText('总览');
});

test('旧的菜单推荐与采购预测地址跳到合并后的页面', async ({ page }) => {
  await loginAs(page, 'recorder');

  await page.goto('/admin/recommendation');
  await expect(page).toHaveURL(/\/admin\/menu-plan$/);

  await page.goto('/admin/forecast');
  await expect(page).toHaveURL(/\/admin\/menu-plan$/);
  await expect(page.getByRole('heading', { name: '明日菜单与采购', exact: true })).toBeVisible();
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

import { expect, test } from '@playwright/test';
import { loginAs } from './helpers';

test('菜品详情展示图片、配方与接口营养结果，学校管理方可查看但不可编辑', async ({ page }) => {
  await loginAs(page, 'school');
  await page.goto('/admin/dishes');
  const card = page.locator('.zw-dish-card').first();
  const name = await card.locator('h2').innerText();
  await card.getByRole('button', { name: `查看${name}详情`, exact: true }).click();
  const drawer = page.locator('.zw-dish-detail-drawer');
  await expect(drawer.getByRole('heading', { name, exact: true })).toBeVisible();
  await expect(drawer.getByRole('heading', { name: '单份营养', exact: true })).toBeVisible();
  await expect(drawer.locator('.zw-dish-recipe-columns li').first()).toBeVisible();
  await expect(drawer.getByRole('button', { name: '编辑配方' })).toHaveCount(0);
  await expect(drawer.getByRole('heading', { name: '菜品说明与制作备注' })).toBeVisible();
});

test('筛选、视图和浏览位置在离开页面与刷新后保留', async ({ page }) => {
  await loginAs(page, 'recorder');
  await page.goto('/admin/dishes');
  const categories = page.getByRole('group', { name: '菜品分类导航' });
  const cards = page.locator('.zw-dish-card');
  await expect(cards.first()).toBeVisible();
  await categories.getByRole('button', { name: '半荤', exact: true }).click();
  const response = await page.request.get('/api/v1/dishes?category=HALF_MEAT&page_size=12');
  expect(response.ok()).toBeTruthy();
  const filtered = await response.json();
  await expect(page.locator('.zw-dish-card')).toHaveCount(filtered.items.length);
  const categoryLabels = await page.locator('.zw-dish-card .zw-tag-sage').allTextContents();
  expect(categoryLabels.length).toBeGreaterThan(0);
  expect(categoryLabels.every((label) => label.trim() === '半荤')).toBe(true);
  await page.evaluate(() => window.scrollTo(0, 450));
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(300);
  await page
    .locator('.zw-admin-menu')
    .getByRole('menuitem', { name: /食材库/ })
    .click();
  await page
    .locator('.zw-admin-menu')
    .getByRole('menuitem', { name: /菜品与配方/ })
    .click();
  await expect(categories.getByRole('button', { name: '半荤', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(300);
  await page.reload();
  await expect(categories.getByRole('button', { name: '半荤', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await page.getByText('列表', { exact: true }).click();
  await page.reload();
  await expect(page.getByRole('table')).toBeVisible();
});

test('配方用量无效时禁止提交，未保存的编辑可以继续', async ({ page }) => {
  await loginAs(page, 'recorder');
  await page.goto('/admin/dishes');
  await page.locator('.zw-dish-card').first().getByRole('button', { name: '查看配方' }).click();
  await page.getByRole('button', { name: '编辑配方', exact: true }).click();
  await expect(page.getByText('已保存的单份营养', { exact: true })).toBeVisible();
  let writes = 0;
  await page.route('**/api/v1/dishes/*/recipe', async (route) => {
    if (route.request().method() === 'PUT') {
      writes += 1;
      await route.abort();
    } else await route.continue();
  });
  await page.getByLabel('配方用量', { exact: true }).first().fill('0');
  await page.getByRole('button', { name: '保存', exact: true }).click();
  await expect(
    page.getByText('请为每行选择用料并填写大于 0 的用量，同一用料不能重复添加。'),
  ).toBeVisible();
  expect(writes).toBe(0);
  await page.getByRole('button', { name: '取消', exact: true }).click();
  await expect(page.locator('.ant-modal-confirm-title')).toHaveText('放弃未保存的修改？');
  await page.getByRole('button', { name: '继续编辑', exact: true }).click();
  await expect(page.getByLabel('配方用量', { exact: true }).first()).toHaveValue(/^0(?:\.0+)?$/);
});

test('手机详情和配方编辑没有横向溢出', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await loginAs(page, 'recorder');
  await page.goto('/admin/dishes');
  await page.locator('.zw-dish-card').first().getByRole('button', { name: '查看配方' }).click();
  await expect(page.locator('.zw-dish-detail-drawer')).toBeVisible();
  await page.getByRole('button', { name: '编辑配方', exact: true }).click();
  await expect(page.getByLabel('配方用量', { exact: true }).first()).toBeVisible();
  const body = page.locator('.zw-dish-form-drawer .ant-drawer-body');
  expect(await body.evaluate((node) => node.scrollWidth <= node.clientWidth + 1)).toBe(true);
  expect(
    (await page.getByLabel('配方用量', { exact: true }).first().boundingBox())!.width,
  ).toBeGreaterThan(120);
});

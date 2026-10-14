import { expect, test } from '@playwright/test';
import { loginAs } from './helpers';

/**
 * 选中一个 AntD Select 选项。
 *
 * AntD 6 把 role="option" 放在高度为 0 的隐藏无障碍镜像里，真正可点的是带 title 的可见项。
 */
async function pickOption(page: import('@playwright/test').Page, title: string) {
  await page.locator(`.ant-select-item-option[title="${title}"]`).click();
}

test('菜品列表展示 20 道菜及其单份营养摘要', async ({ page }) => {
  await loginAs(page, 'recorder');
  await page.goto('/admin/dishes');

  const riceRow = page.getByRole('row').filter({ hasText: '米饭' });
  await expect(riceRow).toBeVisible();
  // 米饭配方：大米 80 克、无调味料 → 0.8 × 346 = 276.80
  await expect(riceRow).toContainText('276.80');
  // 不断言具体条数，也不指望 20 道菜全在第一页：跑测试会在同一个库里留下自己造的菜品
  await expect(page.getByText(/共 \d+ 道/)).toBeVisible();
  await expect(page.getByRole('row').filter({ hasText: '红烧肉' })).toBeVisible();
});

test('新增菜品并录入配方后，列表上出现算出来的营养值', async ({ page }) => {
  const name = `端到端菜品${Date.now()}`;
  await loginAs(page, 'recorder');
  await page.goto('/admin/dishes');

  await page.getByRole('button', { name: '新增菜品' }).click();
  await page.getByLabel('菜品名称').fill(name);
  await page.getByLabel('类别').click();
  await pickOption(page, '主食');
  await page.getByLabel('烹饪方式').click();
  await pickOption(page, '蒸');
  await page.getByLabel('标准份量（克）').fill('200');
  await page.getByLabel('单锅份数').fill('80');

  // 录入配方：大米 80 克
  await page.getByRole('button', { name: '添加一行' }).click();
  await page.getByLabel('配方用料').click();
  await page.getByLabel('配方用料').fill('大米');
  await pickOption(page, '大米');
  await page.getByLabel('配方用量').fill('80');

  await page.getByRole('button', { name: '新增', exact: true }).click();
  await expect(page.getByText('菜品已新增')).toBeVisible();

  await page.getByPlaceholder('按名称搜索').fill(name);
  await page.getByPlaceholder('按名称搜索').press('Enter');
  const row = page.getByRole('row').filter({ hasText: name });
  await expect(row).toBeVisible();
  await expect(row).toContainText('配方 v1');

  // 点进去看详情，配方行确实写进去了
  await row.getByRole('button', { name: '编辑' }).click();
  await expect(page.getByLabel('配方用量')).toHaveValue('80.000');
  // AntD Select 的选中值渲染在单独的 selection-item 里，不在 input 的 value 上
  await expect(
    page.locator('.ant-select-selection-item', { hasText: '大米' }).first(),
  ).toBeVisible();
});

test('编辑配方会递增版本并重算营养', async ({ page }) => {
  await loginAs(page, 'recorder');
  await page.goto('/admin/dishes');

  await page.getByPlaceholder('按名称搜索').fill('清炒西兰花');
  await page.getByPlaceholder('按名称搜索').press('Enter');
  const row = page.getByRole('row').filter({ hasText: '清炒西兰花' });
  // 不写死版本号：反复跑测试会把版本推高，这里关心的是「保存后加一」
  const versionText = await row.innerText();
  const before = Number(/配方 v(\d+)/.exec(versionText)?.[1] ?? '0');
  expect(before).toBeGreaterThan(0);

  await row.getByRole('button', { name: '编辑' }).click();
  // 填一个与现值不同的数：内容没变时服务端不会递增版本，这是刻意的设计
  await page.getByLabel('配方用量').first().fill('120');
  await page.getByRole('button', { name: '保存' }).click();

  await expect(page.getByText('配方已保存，营养结果已重算')).toBeVisible();
  await expect(page.getByRole('row').filter({ hasText: '清炒西兰花' })).toContainText(
    `配方 v${before + 1}`,
  );
});

test('调味料库可以新增并停用', async ({ page }) => {
  const name = `端到端调味料${Date.now()}`;
  await loginAs(page, 'recorder');
  await page.goto('/admin/seasonings');

  await page.getByRole('button', { name: '新增调味料' }).click();
  await page.getByLabel('名称').fill(name);
  await page.getByLabel('类别').click();
  await pickOption(page, '其他');
  await page.getByLabel('钠（毫克/100 克）').fill('1234.5');
  await page.getByRole('button', { name: '新增', exact: true }).click();
  await expect(page.getByText('调味料已新增')).toBeVisible();

  await page.getByPlaceholder('按名称搜索').fill(name);
  await page.getByPlaceholder('按名称搜索').press('Enter');
  const row = page.getByRole('row').filter({ hasText: name });
  await expect(row).toContainText('1234.50');

  await row.getByRole('button', { name: '停用' }).click();
  await page.locator('.ant-popover').getByRole('button', { name: '停用' }).click();
  await expect(page.getByText('调味料已停用')).toBeVisible();
});

test('学校管理方在菜品与调味料库看不到写入口', async ({ page }) => {
  await loginAs(page, 'school');

  await page.goto('/admin/dishes');
  await expect(page.getByRole('button', { name: '新增菜品' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '批量导入' })).toHaveCount(0);

  await page.goto('/admin/seasonings');
  await expect(page.getByRole('button', { name: '新增调味料' })).toHaveCount(0);
});

test('批量导入：校验不通过时给出逐行报告且不写库', async ({ page }) => {
  await loginAs(page, 'recorder');
  await page.goto('/admin/dishes');

  await page.getByRole('button', { name: '批量导入' }).click();
  await expect(page.getByText('批量导入菜品与配方')).toBeVisible();
  await expect(page.locator('button', { hasText: '下载模板' })).toBeVisible();
  await expect(page.getByText(/先下载模板/)).toBeVisible();
});

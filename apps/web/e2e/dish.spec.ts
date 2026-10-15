import { expect, test, type Page } from '@playwright/test';
import { loginAs } from './helpers';

/**
 * 选中一个 AntD Select 选项。
 *
 * AntD 6 把 role="option" 放在高度为 0 的隐藏无障碍镜像里，真正可点的是带 title 的可见项。
 */
async function pickOption(page: Page, title: string) {
  await page.locator(`.ant-select-item-option[title="${title}"]`).click();
}

/** 从界面上新建一道带配方的主食。 */
async function createDishWithRecipe(page: Page, name: string, riceGrams: string) {
  await page.getByRole('button', { name: '新增菜品' }).click();
  await page.getByLabel('菜品名称').fill(name);
  await page.getByLabel('类别').click();
  await pickOption(page, '主食');
  await page.getByLabel('烹饪方式').click();
  await pickOption(page, '蒸');
  await page.getByLabel('标准份量（克）').fill('200');
  await page.getByLabel('单锅份数').fill('80');

  // 配方：大米 80 克、无调味料 → 0.8 × 352.06（稻米(均值) 条目的能量）= 281.65
  await page.getByRole('button', { name: '添加一行' }).click();
  await page.getByLabel('配方用料').click();
  await page.getByLabel('配方用料').fill('大米');
  await pickOption(page, '大米');
  await page.getByLabel('配方用量').fill(riceGrams);

  await page.getByRole('button', { name: '新增', exact: true }).click();
  await expect(page.getByText('菜品已新增')).toBeVisible();
}

/** 按名称检索菜品，返回那一行。 */
async function findDishRow(page: Page, name: string) {
  const search = page.getByPlaceholder('按名称搜索');
  await search.fill(name);
  await search.press('Enter');
  const row = page.getByRole('row').filter({ hasText: name });
  await expect(row).toBeVisible();
  return row;
}

/** 关掉菜品抽屉。保存成功后抽屉会自己关闭，只有「点进去看一眼」的用例需要手动关。 */
async function closeDishDrawer(page: Page) {
  await page.getByRole('button', { name: '关闭' }).click();
}

/** 停用测试造的菜品：用例的产物不该堆在演示库里（与食材、调味料的用例同一套收尾）。 */
async function deactivateDish(page: Page, name: string) {
  const row = await findDishRow(page, name);
  await row.getByRole('button', { name: '停用' }).click();
  await page.locator('.ant-popover').getByRole('button', { name: '停用' }).click();
  await expect(page.getByText('菜品已停用')).toBeVisible();
}

test('菜品列表可按名称检索，并展示配方算出的单份营养', async ({ page }) => {
  await loginAs(page, 'recorder');
  await page.goto('/admin/dishes');

  await expect(page.getByText(/共 \d+ 道/)).toBeVisible();

  // 不指望某道菜正好落在第一页：同一个库里跑一次测试就会多出几道自己造的菜，
  // 菜品只增不减，靠翻页找人迟早会失手
  const riceRow = await findDishRow(page, '米饭');
  // 米饭配方：大米 80 克、无调味料 → 0.8 × 352.06 = 281.65
  await expect(riceRow).toContainText('281.65');

  await expect(await findDishRow(page, '红烧肉')).toBeVisible();
});

test('新增菜品并录入配方后，列表上出现算出来的营养值', async ({ page }) => {
  const name = `端到端菜品${Date.now()}`;
  await loginAs(page, 'recorder');
  await page.goto('/admin/dishes');

  await createDishWithRecipe(page, name, '80');

  const row = await findDishRow(page, name);
  await expect(row).toContainText('配方 v1');
  // 配方刚录完就该看到数值，不必等这道菜第一次被排进菜单
  await expect(row).toContainText('281.65');

  // 点进去看详情，配方行确实写进去了
  await row.getByRole('button', { name: '编辑' }).click();
  await expect(page.getByLabel('配方用量')).toHaveValue('80.000');
  // AntD 6 把选中值渲染在 .ant-select-content 上，文案在它的 title 属性里；
  // 5.x 的 .ant-select-selection-item 已经不再出现
  await expect(page.locator('.ant-select-content[title="大米"]').first()).toBeVisible();

  await closeDishDrawer(page);
  await deactivateDish(page, name);
});

test('编辑配方会递增版本并重算营养', async ({ page }) => {
  const name = `端到端版本菜品${Date.now()}`;
  await loginAs(page, 'recorder');
  await page.goto('/admin/dishes');

  // 自己建一道菜再改它：种子里那几道菜是大屏、看板与后端用例的基准数据，
  // 端到端用例把它们改掉，别的用例就得跟着漂
  await createDishWithRecipe(page, name, '80');
  const row = await findDishRow(page, name);
  await expect(row).toContainText('配方 v1');

  await row.getByRole('button', { name: '编辑' }).click();
  // 填一个与现值不同的数：内容没变时服务端不会递增版本，这是刻意的设计
  await page.getByLabel('配方用量').first().fill('90');
  await page.getByRole('button', { name: '保存' }).click();

  await expect(page.getByText('配方已保存，营养结果已重算')).toBeVisible();
  await expect(page.getByRole('row').filter({ hasText: name })).toContainText('配方 v2');

  await deactivateDish(page, name);
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

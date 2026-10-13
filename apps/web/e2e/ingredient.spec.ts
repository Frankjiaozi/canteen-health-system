import { expect, test } from '@playwright/test';

const DEMO_PASSWORD = 'canteen@2026';

async function loginAsRecorder(page: import('@playwright/test').Page) {
  await page.goto('/login');
  await page.getByLabel('登录名').fill('recorder');
  await page.getByLabel('口令').fill(DEMO_PASSWORD);
  await page.getByRole('button', { name: '登录' }).click();
  await expect(page).toHaveURL(/\/admin$/);
}

test('录入员可以新增、编辑并停用食材', async ({ page }) => {
  const name = `端到端食材${Date.now()}`;
  await loginAsRecorder(page);

  await page.goto('/admin/ingredients');
  const searchBox = page.getByPlaceholder('按名称或数据来源搜索');
  await expect(searchBox).toBeVisible();

  // 新增
  await page.getByRole('button', { name: '新增食材' }).click();
  await expect(page.getByLabel('食材名称')).toBeVisible();
  await page.getByLabel('食材名称').fill(name);
  await page.getByLabel('类别').click();
  // AntD 6 的可访问 role="option" 位于一个高度为 0 的隐藏镜像里，
  // 真正可点的是带 title 的可见选项项
  await page.locator('.ant-select-item-option[title="蔬菜类"]').click();
  await page.getByLabel('能量（千卡/100 克）').fill('30.5');
  await page.getByLabel('数据来源').fill('端到端测试构造');
  await page.getByRole('button', { name: '新增', exact: true }).click();

  await expect(page.getByText('食材已新增')).toBeVisible();

  // 搜索到刚建的食材
  await searchBox.fill(name);
  await searchBox.press('Enter');
  const row = page.getByRole('row').filter({ hasText: name });
  await expect(row).toBeVisible();
  await expect(row).toContainText('30.50');

  // 编辑
  await row.getByRole('button', { name: '编辑' }).click();
  await page.getByLabel('钠（毫克/100 克）').fill('88.80');
  await page.getByRole('button', { name: '保存' }).click();
  await expect(page.getByText('食材已更新')).toBeVisible();
  await expect(page.getByRole('row').filter({ hasText: name })).toContainText('88.80');

  // 停用（软删除）：默认列表不再显示
  await page
    .getByRole('row')
    .filter({ hasText: name })
    .getByRole('button', { name: '停用' })
    .click();
  await page.locator('.ant-popover').getByRole('button', { name: '停用' }).click();
  await expect(page.getByText('食材已停用')).toBeVisible();

  await page.reload();
  await searchBox.fill(name);
  await searchBox.press('Enter');
  // 停用后默认列表不应再出现这一行
  await expect(page.getByRole('row').filter({ hasText: name })).toHaveCount(0);
});

test('学校管理方在食材库看不到任何写操作入口', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('登录名').fill('school');
  await page.getByLabel('口令').fill(DEMO_PASSWORD);
  await page.getByRole('button', { name: '登录' }).click();
  // 等登录真正完成再跳转，否则导航会把还没落地的请求打断
  await expect(page).toHaveURL(/\/admin$/);

  await page.goto('/admin/ingredients');
  await expect(page.getByPlaceholder('按名称或数据来源搜索')).toBeVisible();

  await expect(page.getByRole('button', { name: '新增食材' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '编辑' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '停用' })).toHaveCount(0);
});

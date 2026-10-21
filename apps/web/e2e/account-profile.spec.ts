import { expect, test } from '@playwright/test';
import { loginAs } from './helpers';

for (const username of ['recorder', 'canteen', 'school']) {
  test(`${username} 展示真实账号信息及现有操作权限`, async ({ page }) => {
    await loginAs(page, username);
    const me = await (await page.request.get('/api/v1/auth/me')).json();
    const entry = page.locator('.zw-account-entry');
    await expect(entry).toContainText(me.display_name);
    await expect(entry).toContainText(me.role_label);
    await entry.click();
    const profile = page.getByRole('dialog', { name: '我的账号' });
    await expect(profile).toContainText(`@${username}`);
    await expect(profile).toContainText(username === 'school' ? '查询与分析' : '规划与查询');
    await profile.getByRole('button', { name: '关闭', exact: true }).click();
    await page.goto('/admin/dishes');
    if (username === 'school') {
      await expect(page.getByRole('button', { name: /新增菜品/ })).toHaveCount(0);
      await expect(page.locator('.zw-role-notice')).toContainText('只读');
    } else {
      await expect(page.getByRole('button', { name: /新增菜品/ })).toBeVisible();
    }
  });
}

test('头像仅存本浏览器，刷新保留且不同账号不串用', async ({ page }) => {
  await loginAs(page, 'canteen');
  await page.locator('.zw-account-entry').click();
  const profile = page.getByRole('dialog', { name: '我的账号' });
  await profile.locator('input[type=file]').setInputFiles({
    name: 'avatar.png',
    mimeType: 'image/png',
    buffer: Buffer.from(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j7v8AAAAASUVORK5CYII=',
      'base64',
    ),
  });
  await expect(page.locator('.zw-account-entry img')).toHaveAttribute(
    'src',
    /^data:image\/png;base64,/,
  );
  await page.reload();
  await expect(page.locator('.zw-account-entry img')).toHaveAttribute(
    'src',
    /^data:image\/png;base64,/,
  );
  await page.locator('.zw-account-entry').click();
  await page.getByRole('button', { name: '退出登录', exact: true }).click();
  await loginAs(page, 'school');
  await expect(page.locator('.zw-account-entry img')).toHaveCount(0);
});

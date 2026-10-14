import { expect, test } from '@playwright/test';
import dayjs from 'dayjs';

const DEMO_PASSWORD = 'canteen@2026';

async function login(page: import('@playwright/test').Page, username = 'recorder') {
  await page.goto('/login');
  await page.getByLabel('登录名').fill(username);
  await page.getByLabel('口令').fill(DEMO_PASSWORD);
  await page.getByRole('button', { name: '登录' }).click();
  await expect(page).toHaveURL(/\/admin/);
}

test('生成菜单建议后能看到菜单、营养差距与推荐理由', async ({ page }) => {
  await login(page);
  const target = dayjs().add(1, 'day').format('YYYY-MM-DD');
  await page.goto(`/admin/recommendation?date=${target}&meal=LUNCH`);

  await page.getByRole('button', { name: '生成建议' }).click();
  await expect(page.getByText(/已生成 \d+ 道菜的菜单建议/)).toBeVisible();

  // 菜单本身
  await expect(page.getByText(new RegExp(`${target} 午餐菜单建议`))).toBeVisible();
  await expect(page.getByRole('columnheader', { name: '建议份数' })).toBeVisible();

  // 差距要给出缺口多大，不是只有一个标签
  await expect(page.getByText('与营养目标的差距')).toBeVisible();
  await expect(page.getByText(/实际 [\d.]+/).first()).toBeVisible();

  // 理由要逐条列出来
  await expect(page.getByText('推荐理由')).toBeVisible();
  await expect(page.getByText(/受欢迎度/).first()).toBeVisible();

  // 能量目标还没核实，界面上必须标出来
  await expect(page.getByText('能量目标尚未核实')).toBeVisible();

  // 与服务端对账
  const body = await (
    await page.request.post(`/api/v1/recommendation/generate?on_date=${target}&meal_type=LUNCH`)
  ).json();
  expect(body.gaps.length).toBeGreaterThan(0);
  expect(body.reasons.length).toBeGreaterThan(0);
  expect(body.target_basis.energy_verified).toBe(false);
});

test('否决必须写明原因，写了才记录得下来', async ({ page }) => {
  await login(page, 'canteen');
  const target = dayjs().add(2, 'day').format('YYYY-MM-DD');
  await page.goto(`/admin/recommendation?date=${target}&meal=LUNCH`);

  await page.getByRole('button', { name: '生成建议' }).click();
  await expect(page.getByText(/已生成 \d+ 道菜的菜单建议/)).toBeVisible();

  await page.getByRole('button', { name: '否决' }).click();
  await expect(page.getByText(/写清原因/)).toBeVisible();
  await page.getByPlaceholder(/周五学生普遍不留校/).fill('当天有校外活动，学生不在校用餐');
  await page.getByRole('button', { name: '确认否决' }).click();

  await expect(page.getByText('已否决并记录原因')).toBeVisible();
  await expect(page.getByText(/否决原因：当天有校外活动/)).toBeVisible();
});

test('学校管理方看不到生成与采纳入口', async ({ page }) => {
  await login(page, 'school');
  await page.goto('/admin/recommendation');

  await expect(page.getByText('菜单推荐')).toBeVisible();
  await expect(page.getByRole('button', { name: '生成建议' })).toHaveCount(0);
});

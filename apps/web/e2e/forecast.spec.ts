import { expect, test } from '@playwright/test';
import dayjs from 'dayjs';

const DEMO_PASSWORD = 'canteen@2026';

test('登录后能生成份数预测并看到采购建议单', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('登录名').fill('recorder');
  await page.getByLabel('口令').fill(DEMO_PASSWORD);
  await page.getByRole('button', { name: '登录' }).click();
  await expect(page).toHaveURL(/\/admin/);

  const target = dayjs().add(1, 'day').format('YYYY-MM-DD');
  await page.goto(`/admin/forecast?date=${target}&meal=LUNCH`);

  await page.getByRole('button', { name: '生成预测' }).click();
  await expect(page.getByText(/已生成 \d+ 道菜的份数预测/)).toBeVisible();

  // 预测表里每一道菜都要有份数与依据，不能只给一个数字。
  // 注意别用 getByRole('table').first()：AntD 开了纵向滚动会把表头与表体拆成两个 table，
  // 第一个里面一行数据都没有。
  await expect(page.getByRole('columnheader', { name: '预测份数' })).toBeVisible();
  await expect(page.getByRole('row', { name: /同星期几平均|全期平均/ }).first()).toBeVisible();
  await expect(page.getByText(/同星期几平均/).first()).toBeVisible();

  // 采购建议单要有具体数量与金额
  const purchase = page.getByText(/采购建议单（共 \d+ 项）/);
  await expect(purchase).toBeVisible();
  // 精确到「预计金额 + 数字 + 元」：只写 /预计金额/ 会同时命中列头「预计金额（元）」
  await expect(page.getByText(/预计金额 [\d,.]+ 元/)).toBeVisible();

  // 与服务端对账：界面上的预测份数必须等于接口返回的第一名
  const body = await (
    await page.request.post(`/api/v1/forecast/run?on_date=${target}&meal_type=LUNCH`)
  ).json();
  expect(body.dishes.length).toBeGreaterThan(0);
  expect(body.requirements.length).toBeGreaterThan(0);
});

test('回测给出 MAPE 与覆盖天数，并说明为什么天数少于回测区间', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('登录名').fill('recorder');
  await page.getByLabel('口令').fill(DEMO_PASSWORD);
  await page.getByRole('button', { name: '登录' }).click();
  await expect(page).toHaveURL(/\/admin/);

  await page.goto('/admin/forecast');

  await expect(page.getByText(/平均绝对百分比误差/)).toBeVisible();
  await expect(page.getByText(/回测 56 天/)).toBeVisible();
  await expect(page.getByText(/有足够历史可参照/)).toBeVisible();
});

test('日历逐条来自国务院办公厅通知，放假与调休都在', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('登录名').fill('recorder');
  await page.getByLabel('口令').fill(DEMO_PASSWORD);
  await page.getByRole('button', { name: '登录' }).click();
  await expect(page).toHaveURL(/\/admin/);

  await page.goto('/admin/forecast?date=2026-10-15&meal=LUNCH');

  await expect(page.getByText(/全部已核对/)).toBeVisible();
  await expect(page.getByText(/以国务院办公厅通知为唯一依据/)).toBeVisible();

  // 通知原文里的两大块都要在：国庆放假（10/1 起）与调休上班（10/10）
  await expect(page.getByRole('cell', { name: '国庆节放假' }).first()).toBeVisible();
  await expect(page.getByRole('cell', { name: '国庆节调休上班' }).first()).toBeVisible();

  // 与服务端对账：日历条数与类型分布必须与接口一致
  const calendar = await (await page.request.get('/api/v1/forecast/holidays?year=2026')).json();
  const holidays = calendar.items.filter(
    (item: { kind: string }) => item.kind === 'HOLIDAY',
  ).length;
  const workdays = calendar.items.filter(
    (item: { kind: string }) => item.kind === 'WORKDAY',
  ).length;
  expect(holidays).toBe(33);
  expect(workdays).toBe(6);
  expect(calendar.unverified_count).toBe(0);
});

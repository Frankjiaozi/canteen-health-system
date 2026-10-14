import { expect, test } from '@playwright/test';
import dayjs from 'dayjs';

const DEMO_PASSWORD = 'canteen@2026';

/**
 * 离线队列的验收标准：断网状态下完成一次采集录入，恢复网络后自动同步，大屏能看到结果。
 *
 * 与其它采集用例错开日期，避免并发跑时互相覆盖。
 */
const TARGET = () => dayjs().add(4, 'day').format('YYYY-MM-DD');

test('断网时录入进本地队列，恢复网络后自动补交', async ({ page, context }) => {
  const target = TARGET();

  await page.goto('/login');
  await page.getByLabel('登录名').fill('recorder');
  await page.getByLabel('口令').fill(DEMO_PASSWORD);
  await page.getByRole('button', { name: '登录' }).click();
  await expect(page).toHaveURL(/\/admin/);

  await page.goto(`/admin/collection?date=${target}&meal=LUNCH`);

  // 先在联网状态下把表填好（页面本身要靠网络加载）
  const beefRow = page.getByRole('row', { name: /土豆炖牛肉/ });
  const cabbageRow = page.getByRole('row', { name: /醋溜白菜/ });
  await beefRow.getByRole('checkbox').first().check();
  await cabbageRow.getByRole('checkbox').first().check();
  await page.getByLabel('就餐人次').fill('180');
  await page.getByLabel('食用油').fill('700');
  await page.getByLabel('食盐').fill('260');
  await page.getByLabel('添加糖').fill('90');
  await beefRow.getByRole('spinbutton').first().fill('120');
  await cabbageRow.getByRole('spinbutton').first().fill('130');

  // 断网再提交：数据不能白填
  await context.setOffline(true);
  await page.getByRole('button', { name: '保存并重算营养' }).click();

  await expect(page.getByText(/已存入本地队列/)).toBeVisible();
  await expect(page.getByText('待同步的采集单')).toBeVisible();
  await expect(page.getByText('网络已断开')).toBeVisible();
  // 提示要说清「没丢」，而不是让人以为提交失败了
  await expect(page.getByText(/自动补交/).first()).toBeVisible();

  // 恢复网络：自动补交，队列清空
  await context.setOffline(false);
  await expect(page.getByText('待同步的采集单')).toHaveCount(0, { timeout: 15000 });
  await expect(page.getByText('网络已断开')).toHaveCount(0);

  // 数据真的落到服务端了，而且大屏能看到这一餐
  const sheet = await (
    await page.request.get(`/api/v1/collection/logs/${target}?meal_type=LUNCH`)
  ).json();
  expect(sheet.saved).toBe(true);
  expect(sheet.diner_count).toBe(180);
  expect(Number(sheet.oil_total_g)).toBe(700);

  const board = await (
    await page.request.get(`/api/v1/public/board/today?on_date=${target}`)
  ).json();
  expect(board.dishes.map((card: { name: string }) => card.name).sort()).toEqual([
    '土豆炖牛肉',
    '醋溜白菜',
  ]);
});

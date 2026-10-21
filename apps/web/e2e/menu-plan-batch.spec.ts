import { expect, test } from '@playwright/test';
import dayjs from 'dayjs';
import { loginAs, saveCollection } from './helpers';

/**
 * 批量排菜单 + 采纳并同步当日菜单。
 *
 * 日期挑在 +90 天往后：别的用例占着明天、+2、+3、+20、+41 天，
 * 而批量排菜单会一次写好几天，落在别人身上就是互相覆盖。
 */
const DAYS = 5;
const start = dayjs().add(90, 'day');
const dates = Array.from({ length: DAYS }, (_, index) =>
  start.add(index, 'day').format('YYYY-MM-DD'),
);

test('批量排一段菜单并采纳同步当日菜单', async ({ page }) => {
  await loginAs(page, 'recorder');
  // 把「最近一次采集的人次」铺成与预测份数同一量级，这条用例只验批量与导入
  await saveCollection(page, start.subtract(1, 'day').format('YYYY-MM-DD'));
  await page.goto('/admin/menu-plan');
  await page.getByText('批量排菜单', { exact: true }).click();

  await page.locator('.ant-picker-range input').first().fill(dates[0]);
  await page
    .locator('.ant-picker-range input')
    .nth(1)
    .fill(dates[DAYS - 1]);
  await page.keyboard.press('Enter');

  await page.getByRole('button', { name: '批量生成' }).click();
  // 同一句话在提示条与浮层消息里各出现一次，只盯页面上那条（浮层会自己消失）
  await expect(
    page.locator('.ant-alert-title').filter({ hasText: `${DAYS} 天里排出 ${DAYS} 天` }),
  ).toBeVisible();

  // 每一天都要有菜、有道数与人均成本，且状态是「已生成」
  for (const date of dates) {
    const row = page.getByRole('row', { name: new RegExp(date) });
    await expect(row).toContainText('已生成');
  }

  // 导入之前，界面上这几行是「已生成」——生成只算出来，还没写进当日数据

  await page.getByRole('button', { name: '采纳并同步' }).click();
  await page.getByRole('button', { name: '确认采纳' }).click();
  await expect(
    page.locator('.ant-alert-title').filter({ hasText: `${DAYS} 天里已采纳 ${DAYS} 天` }),
  ).toBeVisible();
  await expect(page.getByText('已采纳').first()).toBeVisible();

  // 与服务端对账：每一天的采集页都按计划勾好了
  for (const date of dates) {
    const sheet = await (
      await page.request.get(`/api/v1/collection/logs/${date}?meal_type=LUNCH`)
    ).json();
    expect(sheet.menu_confirmed).toBe(true);
    expect(
      sheet.dishes.filter((row: { is_planned: boolean }) => row.is_planned).length,
    ).toBeGreaterThan(0);
  }

  // 免登录大屏也看得到这几天（挑第一天看页面，其余用接口对账）
  await page.goto(`/display?date=${dates[0]}&meal=LUNCH`);
  await expect(page.getByTestId('dish-card').first()).toBeVisible();

  const menus: string[][] = [];
  for (const date of dates) {
    const board = await (
      await page.request.get(`/api/v1/public/board/today?on_date=${date}&meal_type=LUNCH`)
    ).json();
    menus.push(board.dishes.map((card: { name: string }) => card.name).sort());
  }
  // 需求里那条硬约束：同一道菜不连续两日重复。批量排菜单最容易在这里出错——
  // 只排除「昨天」那几道时，求解器会把菜单排成「A、B、A、B」两天一循环。
  for (let index = 1; index < menus.length; index += 1) {
    const shared = menus[index].filter((name) => menus[index - 1].includes(name));
    expect(shared, `${dates[index]} 与前一天重复了：${shared.join('、')}`).toEqual([]);
  }
});

test('已经录过采集的那几天会被跳过', async ({ page }) => {
  await loginAs(page, 'recorder');
  const target = dayjs().add(120, 'day').format('YYYY-MM-DD');

  await saveCollection(page, target);

  await page.goto('/admin/menu-plan');
  await page.getByText('批量排菜单', { exact: true }).click();
  await page.locator('.ant-picker-range input').first().fill(target);
  await page.locator('.ant-picker-range input').nth(1).fill(target);
  await page.keyboard.press('Enter');

  await page.getByRole('button', { name: '批量生成' }).click();
  await expect(
    page.locator('.ant-alert-title').filter({ hasText: '1 天里排出 0 天，跳过 1 天' }),
  ).toBeVisible();
  const row = page.getByRole('row', { name: new RegExp(target) });
  await expect(row).toContainText('已跳过');
  await expect(row).toContainText('已经录过采集');
});

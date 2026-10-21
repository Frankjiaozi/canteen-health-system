import { expect, test } from '@playwright/test';
import dayjs from 'dayjs';
import { loginAs, saveCollection } from './helpers';

/**
 * 「同步至当日数据」这条链路。
 *
 * 需求是这样的场景：**前一天**排好明天的菜单，第二天早上大屏就该显示（采集要到一天结束才录），
 * 录入员打开采集页时供应菜品已经勾好，只需按实际供应核对与修改。
 *
 * 日期挑在别人不碰的地方（+20 天）：采集用例占着明天与 +3 天，菜单用例占着明天与 +2 天。
 */
const TARGET = dayjs().add(20, 'day').format('YYYY-MM-DD');

test('同步之后：采集页按计划勾好，公开大屏不用登录就看得到', async ({ page }) => {
  await loginAs(page, 'recorder');
  // 先把「最近一次采集的人次」铺成与预测份数同一量级：否则人均油盐糖被放大到排不出来
  // （那是系统会明确报出来的数据不一致，不是这条用例要验的东西）
  await saveCollection(page, dayjs(TARGET).subtract(1, 'day').format('YYYY-MM-DD'));

  await page.goto(`/admin/menu-plan?date=${TARGET}&meal=LUNCH`);
  await page.getByText('单日', { exact: true }).click();
  await page.getByRole('button', { name: '生成所选餐次菜单' }).click();
  await expect(page.getByText(/已排出 \d+ 道菜/)).toBeVisible();

  await page.getByRole('button', { name: '同步至当日数据' }).click();
  await page.getByRole('button', { name: '确认同步' }).click();
  await expect(page.getByText(new RegExp(`已写入 ${TARGET} 午餐的当日数据`))).toBeVisible();
  await expect(page.getByText(/已写入 \d{4}-\d{2}-\d{2} 的当日数据/)).toBeVisible();

  // 与服务端对账：这一天真的写进去了，而且不是「已确认菜单」的假象
  const sheet = await (
    await page.request.get(`/api/v1/collection/logs/${TARGET}?meal_type=LUNCH`)
  ).json();
  expect(sheet.menu_confirmed).toBe(true);
  expect(sheet.saved).toBe(false);
  const planned = sheet.dishes.filter((row: { is_planned: boolean }) => row.is_planned);
  expect(planned.length).toBeGreaterThan(0);
  expect(sheet.dishes.length).toBeGreaterThanOrEqual(20);

  // 每日采集：计划里的菜已经勾好、带「计划」标记，整份菜品库都列着（临时换菜有地方勾）
  await page.goto(`/admin/collection?date=${TARGET}&meal=LUNCH`);
  // P0 说明性文案已移除；「计划」标签与勾选状态仍要保留
  await expect(page.getByText(/这份菜单是「明日菜单与采购」排好的计划/)).toHaveCount(0);
  await expect(page.getByText('计划', { exact: true }).first()).toBeVisible();
  const checked = page.locator('input[aria-label^="供应-"]:checked');
  expect(await checked.count()).toBe(planned.length);

  // 公开大屏：免登录页面直接看得到这一天的菜品与营养
  const board = await (
    await page.request.get(`/api/v1/public/board/today?on_date=${TARGET}`)
  ).json();
  expect(board.dishes.length).toBe(planned.length);
  expect(board.dishes[0].nutrients).toHaveLength(5);

  await page.goto(`/display?date=${TARGET}`);
  for (const card of board.dishes) {
    await expect(page.getByText(card.name, { exact: true }).first()).toBeVisible();
  }
  // 油盐糖那几项要等当天采集完才有数——采集之前如实显示「暂无数据」，不拿别处的数顶上
  await expect(page.getByText('暂无数据').first()).toBeVisible();
});

test('已经录过采集的那一天，计划不会再盖上去', async ({ page }) => {
  await loginAs(page, 'recorder');
  // 与上一条用例**不相邻**：前两天一旦排过菜单，「不连续两日重复」会把那几道菜排除，
  // 这让后一天的可选菜变少，可能撞上油盐糖上限（那是模型该有的行为，不是这条用例要验的东西）
  const target = dayjs().add(41, 'day').format('YYYY-MM-DD');

  // 先录一餐（模拟「这一天已经过完了」）。人次按初始化样本数据的量级填：
  // 份数是按历史预测出来的，人次填得过小会把人均油盐糖放大到排不出菜单
  await saveCollection(page, target);

  await page.goto(`/admin/menu-plan?date=${target}&meal=LUNCH`);
  await page.getByText('单日', { exact: true }).click();
  await page.getByRole('button', { name: '生成所选餐次菜单' }).click();
  await expect(page.getByText(/已排出 \d+ 道菜/)).toBeVisible();
  await page.getByRole('button', { name: '同步至当日数据' }).click();
  await page.getByRole('button', { name: '确认同步' }).click();

  // 拒绝的理由要说给用户看，并告诉他该去哪儿改
  await expect(page.getByText(/已经录过采集/)).toBeVisible();
  const sheet = await (
    await page.request.get(`/api/v1/collection/logs/${target}?meal_type=LUNCH`)
  ).json();
  expect(sheet.dishes.filter((row: { is_planned: boolean }) => row.is_planned)).toHaveLength(0);
});

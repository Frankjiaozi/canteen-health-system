import { expect, test } from '@playwright/test';
import dayjs from 'dayjs';
import { loginAs } from './helpers';

// 「明日菜单与采购」把推荐、预测、采购三件事合成了一页。
// 端到端盯三件容易在界面上出错的事：
// 1. 页面默认就落在「明天」，不用每次手动翻日期；
// 2. 采购量的份数口径写在明面上，且与后端算出来的一致；
// 3. 份数依据、回测、日历都还查得到（在折叠区里），不是合并之后就没了。

test('生成明日菜单后，菜品、采购单与份数口径都在', async ({ page }) => {
  await loginAs(page, 'recorder');

  const tomorrow = dayjs().add(1, 'day').format('YYYY-MM-DD');
  await page.goto('/admin/menu-plan');
  // 默认日期必须是明天：这一页回答的就是「明天做什么、买什么」
  await expect(page.getByRole('textbox', { name: /日期/ })).toHaveValue(tomorrow);

  // 默认入口是「一天三餐」；这条用例验的是单餐详情，先切到单餐。
  await page.getByText('单餐', { exact: true }).click();
  await page.getByRole('button', { name: '生成单餐' }).click();
  await expect(page.getByText(/已排出 \d+ 道菜，采购 \d+ 项/)).toBeVisible();

  // ① 菜品推荐：只有菜，没有份数（份数归预测）
  await expect(page.getByText('① 明日菜品推荐')).toBeVisible();
  await expect(page.getByRole('columnheader', { name: '单份能量' }).first()).toBeVisible();
  await expect(page.getByRole('columnheader', { name: '建议份数' })).toHaveCount(0);
  await expect(page.getByText('与营养目标的差距')).toBeVisible();
  await page.getByText(/与营养目标的差距/).click();
  await expect(page.getByText(/实际 [\d.]+/).first()).toBeVisible();
  await expect(page.getByText('推荐理由')).toBeVisible();
  // P0 说明性文案已移除；计算结果和差距仍然保留
  await expect(page.getByText('能量目标尚未核实')).toHaveCount(0);

  // ② 采购建议：公斤计、按金额从大到小
  await expect(page.getByText(/② 明日食材采购建议（共 \d+ 项）/)).toBeVisible();
  await expect(page.getByText(/采购金额 [\d,.]+ 元 \/ 预算 [\d,.]+ 元/).first()).toBeVisible();
  const purchaseTable = page
    .getByRole('columnheader', { name: '预计金额（元）' })
    .locator('xpath=ancestor::table')
    .first();
  const amounts = await purchaseTable.locator('tbody tr td:nth-child(5)').allInnerTexts();
  const numeric = amounts.map((text) => Number(text.replace(/,/g, '')));
  expect(numeric.length).toBeGreaterThan(0);
  expect(numeric).toEqual([...numeric].sort((a, b) => b - a));

  // 与服务端对账：界面上的采购项必须与接口一致，且单位真的是公斤
  const body = await (
    await page.request.post(`/api/v1/menu-plan/generate?on_date=${tomorrow}&meal_type=LUNCH`)
  ).json();
  expect(body.requirements.length).toBeGreaterThan(0);
  expect(body.servings_note).toContain('预测份数');
  for (const row of body.requirements) {
    expect(row.unit).toBe('公斤');
    expect(Number(row.quantity)).toBeLessThan(1000);
  }
});

test('依据与校验里能查到每道菜的份数来源、回测误差与日历', async ({ page }) => {
  await loginAs(page, 'recorder');

  const tomorrow = dayjs().add(1, 'day').format('YYYY-MM-DD');
  await page.goto(`/admin/menu-plan?date=${tomorrow}&meal=LUNCH`);
  await page.getByText('单餐', { exact: true }).click();
  await page.getByRole('button', { name: '生成单餐' }).click();
  await expect(page.getByText(/已排出 \d+ 道菜/)).toBeVisible();

  // 折叠区默认收起：日常点一次按钮不需要看到这些
  await expect(page.getByText('每道菜的份数与依据')).toBeHidden();
  await page.getByText(/③ 依据与校验/).click();

  await expect(page.getByText('每道菜的份数与依据')).toBeVisible();
  await expect(page.getByText(/同星期几平均|全期平均/).first()).toBeVisible();

  // 回测结论要给出 MAPE 与覆盖天数
  await expect(page.getByText('回测：这套算法在历史上有多准')).toBeVisible();
  await expect(page.getByText(/平均绝对百分比误差/)).toBeVisible();
  await expect(page.getByText(/回测 56 天/)).toBeVisible();
  await expect(page.getByText(/有足够历史可参照/)).toBeVisible();

  // 日历核对入口也在这一块里
  await expect(page.getByText(/全部已核对/)).toBeVisible();
  await expect(page.getByRole('cell', { name: '国庆节放假' }).first()).toBeVisible();
  await expect(page.getByRole('cell', { name: '国庆节调休上班' }).first()).toBeVisible();
});

test('否决必须写明原因，写了才记录得下来', async ({ page }) => {
  await loginAs(page, 'canteen');

  const target = dayjs().add(2, 'day').format('YYYY-MM-DD');
  await page.goto(`/admin/menu-plan?date=${target}&meal=LUNCH`);
  await page.getByText('单餐', { exact: true }).click();
  await page.getByRole('button', { name: '生成单餐' }).click();
  await expect(page.getByText(/已排出 \d+ 道菜/)).toBeVisible();

  await page.getByRole('button', { name: '否决' }).click();
  await expect(page.getByText(/写清原因/)).toBeVisible();
  await page.getByPlaceholder(/周五学生普遍不留校/).fill('当天有校外活动，学生不在校用餐');
  await page.getByRole('button', { name: '确认否决' }).click();
  await expect(page.getByText('已否决并记录原因')).toBeVisible();
  await expect(page.getByText(/否决原因：当天有校外活动/)).toBeVisible();
});

test('学校管理方可进入菜单页，但没有生成与采纳入口', async ({ page }) => {
  await loginAs(page, 'school');

  await page.getByRole('menuitem', { name: /菜单与采购/ }).click();

  await expect(page.getByText('明日菜单与采购')).toBeVisible();
  await expect(page.getByRole('button', { name: '生成三餐' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '生成单餐' })).toHaveCount(0);
});

test('一天三餐默认入口生成三餐与合并采购单', async ({ page }) => {
  await loginAs(page, 'recorder');

  await page.goto('/admin/menu-plan');
  await page.getByRole('button', { name: '生成三餐' }).click();

  await expect(page.getByText(/① 三餐安排/)).toBeVisible();
  await expect(page.getByText(/早餐 · \d+ 人次/)).toBeVisible();
  await expect(page.getByText(/午餐 · \d+ 人次/)).toBeVisible();
  await expect(page.getByText(/晚餐 · \d+ 人次/)).toBeVisible();
  await expect(page.getByText(/② 全天食材采购建议/)).toBeVisible();
  await expect(page.getByRole('button', { name: '同步三餐至当日数据' })).toBeVisible();
  await expect(page.getByText(/采购量 = 三餐各自推荐菜/)).toHaveCount(0);
  await expect(page.getByText(/按餐次分别校验/)).toHaveCount(0);
});

test('空状态不重复入口，也不展示流程说明', async ({ page }) => {
  await loginAs(page, 'recorder');
  await page.goto('/admin/menu-plan?date=2028-01-15');

  await expect(page.getByText('一天三餐', { exact: true })).toBeVisible();
  await expect(page.getByText('单餐', { exact: true })).toBeVisible();
  await expect(page.getByText('单日', { exact: true })).toHaveCount(0);
  await expect(page.getByText('暂无菜单方案', { exact: true })).toBeVisible();
  await expect(page.getByText('配菜', { exact: true })).toHaveCount(0);
  await expect(page.getByText('定份数', { exact: true })).toHaveCount(0);
  await expect(page.getByText('出采购', { exact: true })).toHaveCount(0);
});

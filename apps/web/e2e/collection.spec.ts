import { expect, test } from '@playwright/test';
import dayjs from 'dayjs';

const DEMO_PASSWORD = 'canteen@2026';

/**
 * 采集用例挑在**明天**：今天那一份是种子演示数据，大屏、看板与校准拟合都拿它当基准，
 * 动它会连带影响别的用例与演示效果。明天没有任何历史，改起来是干净的。
 */
const TARGET = (offset = 1) => dayjs().add(offset, 'day').format('YYYY-MM-DD');

async function login(page: import('@playwright/test').Page) {
  await page.goto('/login');
  await page.getByLabel('登录名').fill('recorder');
  await page.getByLabel('口令').fill(DEMO_PASSWORD);
  await page.getByRole('button', { name: '登录' }).click();
  await expect(page).toHaveURL(/\/admin/);
}

test('录入一餐之后，公开大屏就能看到这一餐', async ({ page }) => {
  await login(page);
  const target = TARGET();

  // 日期与餐次同步在地址栏上，直接打开某一天即可
  await page.goto(`/admin/collection?date=${target}&meal=LUNCH`);

  // 已经勾上的再勾一次是空操作，所以这条用例重复跑也成立
  const beefRow = page.getByRole('row', { name: /土豆炖牛肉/ });
  const cabbageRow = page.getByRole('row', { name: /醋溜白菜/ });
  await beefRow.getByRole('checkbox').first().check();
  await cabbageRow.getByRole('checkbox').first().check();

  await page.getByLabel('就餐人次').fill('260');
  await page.getByLabel('食用油').fill('900');
  await page.getByLabel('食盐').fill('300');
  await page.getByLabel('添加糖').fill('120');

  await beefRow.getByRole('spinbutton').first().fill('140');
  await cabbageRow.getByRole('spinbutton').first().fill('160');

  await page.getByRole('button', { name: '保存并重算营养' }).click();
  await expect(page.getByText(/已保存 2 道菜/)).toBeVisible();

  // 免登录接口上要能看到这一餐——闭环的验收点就是这个
  const board = await (
    await page.request.get(`/api/v1/public/board/today?on_date=${target}`)
  ).json();
  expect(board.dishes.map((card: { name: string }) => card.name).sort()).toEqual([
    '土豆炖牛肉',
    '醋溜白菜',
  ]);
  expect(board.dishes[0].nutrients.length).toBe(5);
});

test('刚录入的那一餐会出现在最近采集里', async ({ page }) => {
  await login(page);
  // 与上一条用例错开日期：两条用例并发跑，共用一天会互相覆盖
  const target = TARGET(3);

  // 这一条只验列表，不依赖上一条用例是否跑过：自己用接口把数据铺好
  const dishList = await (await page.request.get('/api/v1/dishes?page_size=100')).json();
  const rice = dishList.items.find((item: { name: string }) => item.name === '米饭');
  const saved = await page.request.put(`/api/v1/collection/logs/${target}`, {
    data: {
      meal_type: 'LUNCH',
      diner_count: 200,
      oil_total_g: '100',
      salt_total_g: '80',
      sugar_total_g: '30',
      leftover_weight_g: '500',
      note: null,
      anomaly_flags: [],
      dishes: [{ dish_id: rice.id, servings_produced: '150' }],
    },
  });
  expect(saved.ok()).toBeTruthy();

  await page.goto(`/admin/collection?date=${target}&meal=LUNCH`);

  const recent = page.getByRole('table').last();
  await expect(recent.getByRole('row', { name: new RegExp(target) })).toBeVisible();
  // 列表要能看出这一餐录了多少人次的餐、几道菜
  await expect(recent.getByRole('row', { name: new RegExp(target) })).toContainText('200');
  await expect(recent.getByRole('row', { name: new RegExp(target) })).toContainText('1');
});

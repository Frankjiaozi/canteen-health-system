import { expect, test } from '@playwright/test';
import dayjs from 'dayjs';

const DEMO_PASSWORD = 'canteen@2026';
const TARGET = () => dayjs().add(2, 'day').format('YYYY-MM-DD');

/**
 * 抽样用例先通过接口把这一天的菜单与采集造好，再只走界面录一次实测。
 *
 * 菜单与采集不是这个用例要验的东西（采集链路有自己的 spec），用接口铺好
 * 既让用例不依赖执行顺序，也让这里只盯「抽样录入」这一件事。
 */
test('抽样录入之后，这道菜的三个值都能看到', async ({ page }) => {
  const target = TARGET();

  await page.goto('/login');
  await page.getByLabel('登录名').fill('recorder');
  await page.getByLabel('口令').fill(DEMO_PASSWORD);
  await page.getByRole('button', { name: '登录' }).click();
  await expect(page).toHaveURL(/\/admin/);

  const dishList = await (await page.request.get('/api/v1/dishes?page_size=100')).json();
  const beef = dishList.items.find((item: { name: string }) => item.name === '土豆炖牛肉');
  const cabbage = dishList.items.find((item: { name: string }) => item.name === '醋溜白菜');
  expect(beef).toBeTruthy();
  expect(cabbage).toBeTruthy();

  const saved = await page.request.put(`/api/v1/collection/logs/${target}`, {
    data: {
      meal_type: 'LUNCH',
      diner_count: 200,
      oil_total_g: '1800',
      salt_total_g: '600',
      sugar_total_g: '250',
      leftover_weight_g: '2000',
      note: null,
      anomaly_flags: [],
      dishes: [
        { dish_id: beef.id, servings_produced: '120' },
        { dish_id: cabbage.id, servings_produced: '140' },
      ],
    },
  });
  expect(saved.ok()).toBeTruthy();

  await page.goto(`/admin/calibration?date=${target}&meal=LUNCH`);

  const row = page.getByRole('row', { name: /土豆炖牛肉/ });
  await expect(row).toBeVisible();
  // 重复运行这条用例时，上一轮的实测结果还在，两种状态都算正常起点
  await expect(row).toContainText(/未称重|已套用修正/);

  await row.getByRole('button', { name: /录入实测|重新录入/ }).click();
  // 默认带出推算值，这里只改动能量一项，模拟「称出来比推算多一点」
  await page
    .getByRole('dialog')
    .getByRole('row', { name: /能量/ })
    .getByRole('spinbutton')
    .fill('200');
  await page.getByRole('button', { name: '提交实测' }).click();

  await expect(page.getByText(/已套用整体系数|未套用系数/)).toBeVisible();
  await expect(page.getByRole('row', { name: /土豆炖牛肉/ })).toContainText('已套用修正');

  // 三个值并存：接口上理论值与实测值都能取到，且不相等
  const comparison = await (
    await page.request.get(
      `/api/v1/calibration/comparison?dish_id=${beef.id}&on_date=${target}&meal_type=LUNCH`,
    )
  ).json();
  expect(comparison.theoretical).not.toBeNull();
  expect(comparison.sampled).not.toBeNull();
  expect(comparison.sampled.energy_kcal).not.toBe(comparison.theoretical.energy_kcal);
});

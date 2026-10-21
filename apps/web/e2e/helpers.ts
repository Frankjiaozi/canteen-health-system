import { expect, type Page } from '@playwright/test';

export const DEMO_PASSWORD = 'canteen@2026';

/** 以初始化账号登录并等到管理端首屏就绪。 */
export async function loginAs(page: Page, username: string) {
  await page.goto('/login');
  await page.getByLabel('登录名').fill(username);
  await page.getByLabel('口令').fill(DEMO_PASSWORD);
  await page.getByRole('button', { name: '登录' }).click();
  await expect(page).toHaveURL(/\/admin$/);
}

/**
 * 直接通过接口录一餐，用于把「最近一次采集的人次」铺成想要的值。

 * 菜单推荐拿最近一次采集的人次折算人均供给，而份数是按历史预测的：
 * 人次被别的用例写成 180、份数却是 900 份时，人均油盐糖会被放大到排不出菜单
 * （这正是系统会明确报出来的那种数据不一致）。所以需要人次稳定时，用例自己铺一条。
 */
export async function saveCollection(
  page: Page,
  date: string,
  { dinerCount = 900, servings = '150' }: { dinerCount?: number; servings?: string } = {},
) {
  const dishList = await (await page.request.get('/api/v1/dishes?page_size=100')).json();
  const rice = dishList.items.find((item: { name: string }) => item.name === '米饭');
  const response = await page.request.put(`/api/v1/collection/logs/${date}`, {
    data: {
      meal_type: 'LUNCH',
      diner_count: dinerCount,
      oil_total_g: '1000',
      salt_total_g: '400',
      sugar_total_g: '150',
      leftover_weight_g: '2000',
      note: null,
      anomaly_flags: [],
      dishes: [{ dish_id: rice.id, servings_produced: servings }],
    },
  });
  expect(response.ok()).toBeTruthy();
}

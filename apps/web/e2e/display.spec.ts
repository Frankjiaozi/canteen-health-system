import { expect, test } from '@playwright/test';

test('公开大屏不需要登录就能看到今日菜单与营养', async ({ page }) => {
  await page.goto('/display?meal=LUNCH');

  await expect(page.getByText('今日菜单与营养')).toBeVisible();
  await expect(page.getByText('知味 · 校园智慧膳食平台')).toBeVisible();
  // 免登录：不应被重定向到登录页
  await expect(page).not.toHaveURL(/login/);

  // 菜单按轮换逐日变化，因此不写死菜名：直接与接口返回的内容比对，
  // 这样既不受轮换影响，又能验证「大屏上的数字就是接口里的数字」
  const board = await (await page.request.get('/api/v1/public/board/today?meal_type=LUNCH')).json();
  expect(board.dishes.length).toBeGreaterThan(0);
  const first = board.dishes[0];
  await expect(page.getByText(first.name).first()).toBeVisible();
  await expect(page.getByText(first.nutrients[0].value).first()).toBeVisible();
  // 数值来自哪一层必须写在卡面上：抽样实测和配方推算在大屏上长得一样，
  // 但两者的说服力完全不同，不标出来等于把口径藏起来了
  expect(first.value_type_label).toBeTruthy();
  await expect(page.getByText(first.value_type_label).first()).toBeVisible();
});

test('公开大屏展示膳食指南对照条与合规说明', async ({ page }) => {
  await page.goto('/display?meal=LUNCH');

  await expect(page.getByText('食盐').first()).toBeVisible();
  await expect(page.getByText('烹调油').first()).toBeVisible();
  await expect(page.getByText('添加糖').first()).toBeVisible();
  await expect(page.getByText(/中国居民膳食指南/).first()).toBeVisible();
  await expect(page.getByText(/不针对任何个人/)).toBeVisible();
});

test('公开大屏可以切换早餐、午餐和晚餐', async ({ page }) => {
  await page.goto('/display?meal=BREAKFAST');

  for (const mealType of ['BREAKFAST', 'LUNCH', 'DINNER']) {
    const board = await (
      await page.request.get(`/api/v1/public/board/today?meal_type=${mealType}`)
    ).json();
    await page.getByRole('button', { name: board.meal_label }).click();
    await expect(page).toHaveURL(new RegExp(`meal=${mealType}`));
    await expect(
      page.getByText(`${board.meal_label} · 就餐 ${board.diner_count ?? '—'} 人次`),
    ).toBeVisible();
    if (board.dishes.length > 0) {
      await expect(page.getByText(board.dishes[0].name).first()).toBeVisible();
    }
  }
});

for (const viewport of [
  { name: '1920 大屏', width: 1920, height: 1080 },
  { name: '1366 笔记本', width: 1366, height: 768 },
  { name: '390 手机竖屏', width: 390, height: 844 },
]) {
  test(`公开大屏在${viewport.name}下不溢出`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.goto('/display?meal=LUNCH');
    await expect(page.getByText('今日菜单与营养')).toBeVisible();

    const overflow = await page.evaluate(() => ({
      horizontal: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      vertical: document.documentElement.scrollHeight - document.documentElement.clientHeight,
    }));

    expect(overflow.horizontal).toBeLessThanOrEqual(0);
    expect(overflow.vertical).toBeLessThanOrEqual(0);

    // 光看 document 的滚动高度抓不到这类 bug：大屏用 transform: scale() 套在
    // overflow:hidden 的固定容器里，文档永远不会溢出，内容却可以压在一起。
    // 所以直接量元素框——菜品区必须整体落在指南对照条上方，每张菜卡必须在菜品区之内。
    const grid = await page.getByTestId('dish-grid').boundingBox();
    const bar = await page.getByTestId('standards-bar').boundingBox();
    expect(grid).not.toBeNull();
    expect(bar).not.toBeNull();
    expect(grid!.y + grid!.height).toBeLessThanOrEqual(bar!.y + 1);

    for (const card of await page.getByTestId('dish-card').all()) {
      const box = await card.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.y).toBeGreaterThanOrEqual(grid!.y - 1);
      expect(box!.y + box!.height).toBeLessThanOrEqual(grid!.y + grid!.height + 1);
    }
  });
}

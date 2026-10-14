import { lazy } from 'react';

// 菜品与配方、调味料库的路由片段：需要登录
export const DishListPage = lazy(() =>
  import('./pages/DishListPage').then((m) => ({ default: m.DishListPage })),
);

export const SeasoningListPage = lazy(() =>
  import('./pages/SeasoningListPage').then((m) => ({ default: m.SeasoningListPage })),
);

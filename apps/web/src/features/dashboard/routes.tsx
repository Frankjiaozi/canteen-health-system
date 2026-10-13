import { lazy } from 'react';

// 管理端看板路由片段：需要登录
export const DashboardPage = lazy(() =>
  import('./pages/DashboardPage').then((m) => ({ default: m.DashboardPage })),
);

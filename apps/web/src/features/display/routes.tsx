import { lazy } from 'react';

// 公开大屏路由片段：免登录
export const DisplayPage = lazy(() =>
  import('./pages/DisplayPage').then((m) => ({ default: m.DisplayPage })),
);

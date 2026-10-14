import { lazy } from 'react';

/** 菜单推荐路由片段，由 src/app/router.tsx 汇总挂载。 */
export const RecommendationPage = lazy(() =>
  import('./pages/RecommendationPage').then((m) => ({ default: m.RecommendationPage })),
);

import { lazy } from 'react';

/** 消耗量预测路由片段，由 src/app/router.tsx 汇总挂载。 */
export const ForecastPage = lazy(() =>
  import('./pages/ForecastPage').then((m) => ({ default: m.ForecastPage })),
);

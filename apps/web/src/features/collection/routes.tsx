import { lazy } from 'react';

/** 每日采集路由片段，由 src/app/router.tsx 汇总挂载。 */
export const DailyLogPage = lazy(() =>
  import('./pages/DailyLogPage').then((m) => ({ default: m.DailyLogPage })),
);

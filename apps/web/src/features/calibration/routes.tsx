import { lazy } from 'react';

/** 抽样纠偏路由片段，由 src/app/router.tsx 汇总挂载。 */
export const SamplingPage = lazy(() =>
  import('./pages/SamplingPage').then((m) => ({ default: m.SamplingPage })),
);

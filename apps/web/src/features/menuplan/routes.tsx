import { lazy } from 'react';

/** 「明日菜单与采购」路由片段，由 src/app/router.tsx 汇总挂载。 */
export const MenuPlanPage = lazy(() =>
  import('./pages/MenuPlanPage').then((m) => ({ default: m.MenuPlanPage })),
);

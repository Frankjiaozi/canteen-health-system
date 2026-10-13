import { lazy } from 'react';

/** 食材库路由片段，由 src/app/router.tsx 汇总挂载。 */
export const IngredientListPage = lazy(() =>
  import('./pages/IngredientListPage').then((m) => ({ default: m.IngredientListPage })),
);

import { RouterProvider, createBrowserRouter } from 'react-router-dom';
import { Skeleton } from 'antd';
import { Suspense, lazy } from 'react';

const NotFoundPage = lazy(() =>
  import('@/shared/pages/NotFoundPage').then((m) => ({ default: m.NotFoundPage })),
);

/**
 * 路由表。
 *
 * 约定：各业务域在 `src/features/<域>/routes.tsx` 中导出自己的路由片段，
 * 由本文件汇总挂载；路由级懒加载，避免首屏加载全部业务代码。
 */
const router = createBrowserRouter([
  {
    path: '*',
    element: (
      <Suspense fallback={<Skeleton active style={{ padding: 48 }} />}>
        <NotFoundPage />
      </Suspense>
    ),
  },
]);

export function AppRouter() {
  return <RouterProvider router={router} />;
}

import { Skeleton } from 'antd';
import { Suspense, lazy, type ReactNode } from 'react';
import { Navigate, RouterProvider, createBrowserRouter } from 'react-router-dom';
import { RequireAuth } from '@/features/auth/components/RequireAuth';
import { SamplingPage } from '@/features/calibration/routes';
import { DailyLogPage } from '@/features/collection/routes';
import { DisplayPage } from '@/features/display/routes';
import { MenuPlanPage } from '@/features/menuplan/routes';
import { DashboardPage } from '@/features/dashboard/routes';
import { DishListPage, SeasoningListPage } from '@/features/dish/routes';
import { IngredientListPage } from '@/features/ingredient/routes';
import { AdminLayout } from '@/layouts/AdminLayout';

const NotFoundPage = lazy(() =>
  import('@/shared/pages/NotFoundPage').then((m) => ({ default: m.NotFoundPage })),
);
const LoginPage = lazy(() =>
  import('@/features/auth/pages/LoginPage').then((m) => ({ default: m.LoginPage })),
);
const RegisterPage = lazy(() =>
  import('@/features/auth/pages/RegisterPage').then((m) => ({ default: m.RegisterPage })),
);

// 路由级懒加载的兜底：业务代码按页面分包，首屏不加载全部模块
function lazyElement(node: ReactNode) {
  return <Suspense fallback={<Skeleton active style={{ padding: 48 }} />}>{node}</Suspense>;
}

const router = createBrowserRouter([
  {
    path: '/',
    element: <Navigate to="/admin" replace />,
  },
  {
    path: '/login',
    element: lazyElement(<LoginPage />),
  },
  {
    path: '/register',
    element: lazyElement(<RegisterPage />),
  },
  {
    // 公开大屏：全系统唯一的免登录页面
    path: '/display',
    element: lazyElement(<DisplayPage />),
  },
  {
    path: '/admin',
    element: (
      <RequireAuth>
        <AdminLayout />
      </RequireAuth>
    ),
    children: [
      // 首页就是数据看板：打开系统先看「今天怎么样」，再点进具体模块处理
      { index: true, element: lazyElement(<DashboardPage />) },
      { path: 'ingredients', element: lazyElement(<IngredientListPage />) },
      { path: 'dishes', element: lazyElement(<DishListPage />) },
      { path: 'seasonings', element: lazyElement(<SeasoningListPage />) },
      { path: 'collection', element: lazyElement(<DailyLogPage />) },
      { path: 'calibration', element: lazyElement(<SamplingPage />) },
      { path: 'menu-plan', element: lazyElement(<MenuPlanPage />) },
      // 旧地址留一个跳转，「数据看板」不再单列一项
      { path: 'dashboard', element: <Navigate to="/admin" replace /> },
      // 「菜单推荐」与「采购预测」已合成「明日菜单与采购」，旧地址照旧能用
      { path: 'forecast', element: <Navigate to="/admin/menu-plan" replace /> },
      { path: 'recommendation', element: <Navigate to="/admin/menu-plan" replace /> },
    ],
  },
  {
    path: '*',
    element: lazyElement(<NotFoundPage />),
  },
]);

export function AppRouter() {
  return <RouterProvider router={router} />;
}

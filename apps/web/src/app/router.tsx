import { Skeleton } from 'antd';
import { Suspense, lazy, type ReactNode } from 'react';
import { Navigate, RouterProvider, createBrowserRouter } from 'react-router-dom';
import { RequireAuth } from '@/features/auth/components/RequireAuth';
import { SamplingPage } from '@/features/calibration/routes';
import { DailyLogPage } from '@/features/collection/routes';
import { DisplayPage } from '@/features/display/routes';
import { DashboardPage } from '@/features/dashboard/routes';
import { DishListPage, SeasoningListPage } from '@/features/dish/routes';
import { IngredientListPage } from '@/features/ingredient/routes';
import { AdminLayout } from '@/layouts/AdminLayout';
import { SYSTEM_MODULES } from '@/shared/config/modules';

const NotFoundPage = lazy(() =>
  import('@/shared/pages/NotFoundPage').then((m) => ({ default: m.NotFoundPage })),
);
const AdminHomePage = lazy(() =>
  import('@/shared/pages/AdminHomePage').then((m) => ({ default: m.AdminHomePage })),
);
const PlaceholderPage = lazy(() =>
  import('@/shared/pages/PlaceholderPage').then((m) => ({ default: m.PlaceholderPage })),
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

// 尚未实现的模块统一渲染占位页，文案取自模块清单，保持单一来源
function placeholderElement(path: string) {
  const module = SYSTEM_MODULES.find((item) => item.path === path);
  return lazyElement(
    <PlaceholderPage title={module?.title ?? '建设中'} description={module?.description} />,
  );
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
      { index: true, element: lazyElement(<AdminHomePage />) },
      { path: 'ingredients', element: lazyElement(<IngredientListPage />) },
      { path: 'dishes', element: lazyElement(<DishListPage />) },
      { path: 'seasonings', element: lazyElement(<SeasoningListPage />) },
      { path: 'collection', element: lazyElement(<DailyLogPage />) },
      { path: 'calibration', element: lazyElement(<SamplingPage />) },
      { path: 'dashboard', element: lazyElement(<DashboardPage />) },
      { path: 'forecast', element: placeholderElement('/admin/forecast') },
      { path: 'recommendation', element: placeholderElement('/admin/recommendation') },
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

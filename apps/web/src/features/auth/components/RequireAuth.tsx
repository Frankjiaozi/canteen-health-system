import { Result, Skeleton } from 'antd';
import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useCurrentUser } from '../hooks/useAuth';
import { resolveAuthGate } from '../lib/authGate';
import type { UserRole } from '../types';

interface RequireAuthProps {
  children: ReactNode;
  /** 传入后额外做角色校验；不传表示任何已登录角色都可访问。 */
  allowedRoles?: readonly UserRole[];
}

export function RequireAuth({ children, allowedRoles }: RequireAuthProps) {
  const location = useLocation();
  const { data: user, isPending, error } = useCurrentUser();
  const decision = resolveAuthGate({ isPending, error, user, allowedRoles });

  switch (decision.kind) {
    case 'loading':
      return <Skeleton active style={{ padding: 48 }} />;
    case 'redirect-to-login':
      // 记下来访地址，登录成功后回到原来要去的页面
      return <Navigate to="/login" state={{ from: location }} replace />;
    case 'forbidden':
      return (
        <Result
          status="403"
          title="403"
          subTitle={`当前账号（${decision.role}）没有访问该页面的权限`}
        />
      );
    case 'error':
      return <Result status="error" title="无法获取登录状态" subTitle="请稍后重试" />;
    case 'allow':
      return <>{children}</>;
  }
}

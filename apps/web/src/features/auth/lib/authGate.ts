import { ApiError } from '@/shared/api/errors';
import type { AuthUser, UserRole } from '../types';

// 路由守卫的判定结果。
//
// 抽成纯函数是为了能直接做单元测试：守卫逻辑一旦退化，表现是「该拦的没拦住」
// 或「刚登录就被踢回登录页」，这两种问题靠点界面很难覆盖全。
export type AuthGateDecision =
  | { kind: 'loading' }
  | { kind: 'redirect-to-login' }
  | { kind: 'forbidden'; role: UserRole }
  | { kind: 'error'; error: unknown }
  | { kind: 'allow'; user: AuthUser };

export interface AuthGateInput {
  isPending: boolean;
  error: unknown;
  user: AuthUser | undefined;
  allowedRoles?: readonly UserRole[];
}

export function resolveAuthGate({
  isPending,
  error,
  user,
  allowedRoles,
}: AuthGateInput): AuthGateDecision {
  if (isPending) {
    return { kind: 'loading' };
  }

  if (error) {
    // 只有「未登录 / 登录过期」才跳登录页；服务器故障要如实报错，
    // 否则用户会以为自己没登录，反复输入口令也进不去
    if (error instanceof ApiError && error.isUnauthorized) {
      return { kind: 'redirect-to-login' };
    }
    return { kind: 'error', error };
  }

  if (!user) {
    return { kind: 'redirect-to-login' };
  }

  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return { kind: 'forbidden', role: user.role };
  }

  return { kind: 'allow', user };
}

import { describe, expect, it } from 'vitest';
import { ApiError } from '@/shared/api/errors';
import { resolveAuthGate } from './authGate';
import type { AuthUser } from '../types';

const RECORDER: AuthUser = {
  id: '00000000-0000-0000-0000-000000000001',
  username: 'recorder',
  display_name: '王芳',
  role: 'RECORDER',
  role_label: '食堂录入员',
};

const SCHOOL_ADMIN: AuthUser = { ...RECORDER, username: 'school', role: 'SCHOOL_ADMIN' };

describe('resolveAuthGate', () => {
  it('加载中显示骨架屏，不做跳转', () => {
    expect(resolveAuthGate({ isPending: true, error: null, user: undefined }).kind).toBe('loading');
  });

  it('未登录时跳登录页', () => {
    expect(resolveAuthGate({ isPending: false, error: null, user: undefined }).kind).toBe(
      'redirect-to-login',
    );
  });

  it('401 视为未登录，跳登录页', () => {
    const error = new ApiError(401, { code: 'unauthorized', message: '未登录', details: null });

    expect(resolveAuthGate({ isPending: false, error, user: undefined }).kind).toBe(
      'redirect-to-login',
    );
  });

  it('其它错误如实报错，不假装是未登录', () => {
    const error = new ApiError(503, {
      code: 'service_unavailable',
      message: '数据库连接失败',
      details: null,
    });

    expect(resolveAuthGate({ isPending: false, error, user: undefined }).kind).toBe('error');
  });

  it('已登录且不限定角色时放行', () => {
    const decision = resolveAuthGate({ isPending: false, error: null, user: RECORDER });

    expect(decision.kind).toBe('allow');
  });

  it('角色符合白名单时放行', () => {
    const decision = resolveAuthGate({
      isPending: false,
      error: null,
      user: RECORDER,
      allowedRoles: ['RECORDER', 'CANTEEN_ADMIN'],
    });

    expect(decision.kind).toBe('allow');
  });

  it('角色不在白名单时拒绝', () => {
    const decision = resolveAuthGate({
      isPending: false,
      error: null,
      user: SCHOOL_ADMIN,
      allowedRoles: ['RECORDER', 'CANTEEN_ADMIN'],
    });

    expect(decision.kind).toBe('forbidden');
  });
});

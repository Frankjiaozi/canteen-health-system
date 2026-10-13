import { describe, expect, it } from 'vitest';
import { canWriteBusinessData } from './permissions';
import type { AuthUser } from '../types';

function user(role: AuthUser['role']): AuthUser {
  return {
    id: '00000000-0000-0000-0000-000000000000',
    username: 'u',
    display_name: '测试',
    role,
    role_label: '测试',
  };
}

describe('canWriteBusinessData', () => {
  it('录入员可以写', () => {
    expect(canWriteBusinessData(user('RECORDER'))).toBe(true);
  });

  it('食堂管理员可以写', () => {
    expect(canWriteBusinessData(user('CANTEEN_ADMIN'))).toBe(true);
  });

  it('学校管理方只读', () => {
    expect(canWriteBusinessData(user('SCHOOL_ADMIN'))).toBe(false);
  });

  it('未登录不可写', () => {
    expect(canWriteBusinessData(undefined)).toBe(false);
  });
});

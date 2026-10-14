import type { components } from '@canteen/api-client';

export type AuthUser = components['schemas']['AuthUser'];
export type LoginPayload = components['schemas']['LoginRequest'];
export type RegisterPayload = components['schemas']['RegisterRequest'];
export type UserRole = components['schemas']['UserRole'];

/** 可登录管理端的角色。系统内**没有学生账号**——「学生端」是免登录的公开大屏。 */
export const ALL_ROLES: readonly UserRole[] = ['RECORDER', 'CANTEEN_ADMIN', 'SCHOOL_ADMIN'];

/** 可写业务数据（食材、配方、每日记录）的角色。 */
export const WRITE_ROLES: readonly UserRole[] = ['RECORDER', 'CANTEEN_ADMIN'];

import { WRITE_ROLES } from '../types';
import type { AuthUser } from '../types';

/** 能否写业务数据（食材、配方、每日记录）。学校管理方是只读的观察者。 */
export function canWriteBusinessData(user: AuthUser | undefined): boolean {
  return user !== undefined && WRITE_ROLES.includes(user.role);
}

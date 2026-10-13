import { api } from '@/shared/api/client';
import { unwrap } from '@/shared/api/result';
import type { PublicBoard } from '../types';

// 免登录接口：公开大屏不携带任何身份信息
export async function fetchPublicBoard(): Promise<PublicBoard> {
  return unwrap(await api.GET('/api/v1/public/board/today'));
}

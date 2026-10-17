import { api } from '@/shared/api/client';
import { unwrap } from '@/shared/api/result';
import type { PublicBoard } from '../types';

// 免登录接口：公开大屏不携带任何身份信息
//
// `onDate` 只用于回看与演示（`/display?date=2026-10-16`）：排菜单的人需要能当场看一眼
// 「明天的大屏长什么样」，而不是等到第二天早上才知道。正式挂机的大屏不带这个参数，
// 永远显示当天。
export async function fetchPublicBoard(onDate?: string): Promise<PublicBoard> {
  return unwrap(
    await api.GET('/api/v1/public/board/today', { params: { query: { on_date: onDate } } }),
  );
}

import createClient from 'openapi-fetch';
import type { paths } from './schema';

/** 生产与开发统一走同源路径，由 nginx（生产）或 Vite 代理（开发）转发到后端。 */
export const DEFAULT_API_BASE_URL = '/api/v1';

/**
 * 创建带类型的 API 客户端。
 *
 * - 请求类型与响应类型全部来自 `schema.d.ts`，接口变更会在编译期暴露。
 * - `credentials: 'include'` 让 httpOnly Cookie 随请求发送，前端不接触 token 本身。
 */
export function createApiClient(baseUrl: string = DEFAULT_API_BASE_URL) {
  return createClient<paths>({
    baseUrl,
    credentials: 'include',
  });
}

/** 供业务代码直接使用的单例客户端。 */
export const apiClient = createApiClient();

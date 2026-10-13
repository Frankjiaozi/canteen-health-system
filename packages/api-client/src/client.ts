import createClient from 'openapi-fetch';
import type { paths } from './schema';

/**
 * 默认同源（空字符串）。
 *
 * 后端 OpenAPI 里的路径本身已带 `/api/v1` 前缀（例如 `/api/v1/auth/login`），
 * 因此这里不能再拼 `/api/v1`，否则会变成 `/api/v1/api/v1/...`。
 * 开发期由 Vite 代理、生产由 nginx 把 `/api` 转发到后端。
 */
export const DEFAULT_API_BASE_URL = '';

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

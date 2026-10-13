import { createApiClient } from '@canteen/api-client';

/**
 * 全站唯一的 API 客户端。
 *
 * 传空 baseUrl：后端 OpenAPI 的路径已经带 `/api/v1` 前缀，这里再拼就会重复。
 * `credentials: 'include'` 由 api-client 包统一设置，登录态靠 httpOnly Cookie 传递，
 * 前端代码不接触令牌。
 */
export const api = createApiClient('');

import { ApiError, toApiError } from './errors';

/** openapi-fetch 的返回结构。 */
export interface ApiResult<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

/**
 * 拆开 openapi-fetch 的 `{ data, error }` 结构：成功返回数据，失败抛 `ApiError`。
 *
 * 业务代码因此只需要写 try/catch，不必在每个调用点判断 error 字段。
 */
export function unwrap<T>(result: ApiResult<T>): T {
  if (result.error !== undefined) {
    throw toApiError(result.response?.status ?? 0, result.error);
  }
  if (result.data === undefined) {
    throw new ApiError(result.response?.status ?? 0, {
      code: 'empty_response',
      message: '服务器没有返回数据',
      details: null,
    });
  }
  return result.data;
}

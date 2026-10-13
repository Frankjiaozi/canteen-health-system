/** 后端统一错误体：`{ code, message, details }`。 */
export interface ApiErrorBody {
  code: string;
  message: string;
  details: unknown;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.name = 'ApiError';
    this.status = status;
    this.code = body.code;
    this.details = body.details;
  }

  get isUnauthorized(): boolean {
    return this.status === 401;
  }

  get isForbidden(): boolean {
    return this.status === 403;
  }
}

function isApiErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== 'object' || value === null) return false;
  const candidate = value as Record<string, unknown>;
  return typeof candidate.code === 'string' && typeof candidate.message === 'string';
}

/**
 * 把任意失败响应归一成 `ApiError`。
 *
 * 网络中断、网关返回 HTML 等情况拿不到后端错误体，这里兜一个可读的兜底文案，
 * 界面永远不会因为「错误不是标准结构」而白屏。
 */
export function toApiError(status: number, body: unknown): ApiError {
  if (isApiErrorBody(body)) {
    return new ApiError(status, body);
  }
  return new ApiError(status, {
    code: 'unexpected_response',
    message: status === 0 ? '无法连接服务器，请检查网络' : `请求失败（HTTP ${status}）`,
    details: body ?? null,
  });
}

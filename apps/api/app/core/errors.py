"""领域异常与统一异常处理器。

约定：对外错误响应体一律为 `{code, message, details}`，HTTP 状态码表达语义，
不用 200 包装错误；未预期的异常只对外返回通用文案，细节只进日志。
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

logger = get_logger(__name__)


class AppError(Exception):
    """业务异常基类。

    所有可预期的失败都应抛出它的子类，而不是 FastAPI 的 HTTPException——
    前者能携带稳定的业务错误码，前端可以据此做分支处理。
    """

    code: str = "internal_error"
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_message: str = "服务器内部错误"

    def __init__(self, message: str | None = None, *, details: Any = None) -> None:
        self.message = message or self.default_message
        self.details = details
        super().__init__(self.message)


class NotFoundError(AppError):
    code = "not_found"
    status_code = status.HTTP_404_NOT_FOUND
    default_message = "请求的资源不存在"


class ConflictError(AppError):
    code = "conflict"
    status_code = status.HTTP_409_CONFLICT
    default_message = "数据冲突，请检查后重试"


class UnauthorizedError(AppError):
    code = "unauthorized"
    status_code = status.HTTP_401_UNAUTHORIZED
    default_message = "未登录或登录已过期"


class ForbiddenError(AppError):
    code = "forbidden"
    status_code = status.HTTP_403_FORBIDDEN
    default_message = "当前账号没有执行该操作的权限"


class BusinessRuleError(AppError):
    code = "business_rule_violated"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    default_message = "操作不满足业务规则"


class ServiceUnavailableError(AppError):
    code = "service_unavailable"
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_message = "依赖服务不可用，请稍后重试"


def error_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    """构造统一的错误响应体。"""
    return {"code": code, "message": message, "details": details}


_HTTP_CODE_MAP: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
    429: "too_many_requests",
    500: "internal_error",
    503: "service_unavailable",
}

# Starlette 对 404 / 405 等自动生成的英文 detail，对外应换成中文；
# 而业务代码显式写的中文 detail 必须原样保留，因此只在完全匹配默认英文时替换。
_STARLETTE_DEFAULT_DETAIL: dict[int, str] = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    409: "Conflict",
    422: "Unprocessable Entity",
    429: "Too Many Requests",
    500: "Internal Server Error",
    503: "Service Unavailable",
}

_LOCALIZED_DEFAULT_DETAIL: dict[int, str] = {
    400: "请求格式有误",
    401: "未登录或登录已过期",
    403: "没有访问该资源的权限",
    404: "请求的资源不存在",
    405: "请求方法不被允许",
    409: "数据冲突，请检查后重试",
    422: "请求参数校验失败",
    429: "请求过于频繁，请稍后重试",
    500: "服务器内部错误",
    503: "服务暂时不可用，请稍后重试",
}


def _localize_detail(status_code: int, detail: object) -> str:
    if isinstance(detail, str) and detail == _STARLETTE_DEFAULT_DETAIL.get(status_code):
        return _LOCALIZED_DEFAULT_DETAIL.get(status_code, detail)
    return str(detail)


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器，保证任何失败路径都返回统一结构。"""

    @app.exception_handler(AppError)
    async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        if exc.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
            logger.error("业务异常：%s", exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {
                "field": ".".join(str(part) for part in error["loc"][1:]) or str(error["loc"][0]),
                "message": error["msg"],
                "type": error["type"],
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=error_body("validation_error", "请求参数校验失败", details),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODE_MAP.get(exc.status_code, "http_error")
        headers = getattr(exc, "headers", None)
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(code, _localize_detail(exc.status_code, exc.detail), None),
            headers=headers,
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        # 异常细节只进日志、不进响应体，避免泄露内部实现
        logger.exception("未预期的异常：%s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_body("internal_error", "服务器内部错误", None),
        )

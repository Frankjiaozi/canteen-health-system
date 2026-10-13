"""请求上下文中间件。

为每个请求生成（或沿用上游传入的）request_id，写入日志上下文并回填响应头，
同时输出一条包含耗时与状态码的访问日志。
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import get_logger, request_id_var

logger = get_logger("app.request")

REQUEST_ID_HEADER = "X-Request-ID"


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex[:16]
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.exception("%s %s → 500 (%.1fms)", request.method, request.url.path, elapsed_ms)
            raise
        else:
            elapsed_ms = (time.perf_counter() - started) * 1000
            response.headers[REQUEST_ID_HEADER] = request_id
            logger.info(
                "%s %s → %d (%.1fms)",
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
            )
            return response
        finally:
            request_id_var.reset(token)

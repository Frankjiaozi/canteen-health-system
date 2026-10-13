"""日志配置。

统一使用标准库 logging，输出带时间戳、级别、请求 ID 与 logger 名称的单行文本，
便于内网自部署时直接落盘排查。业务代码禁止使用 print。
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar

# 每个请求一个 request_id，由 RequestContextMiddleware 写入，便于串联一次请求的全部日志
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

_LOG_FORMAT = "%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class RequestIdFilter(logging.Filter):
    """把当前请求 ID 注入到每条日志记录，供格式化串取用。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def configure_logging(level: str = "INFO") -> None:
    """装配根 logger。重复调用是安全的（幂等）。"""
    # Windows 控制台默认按本地代码页编码，中文日志会变成乱码；这里统一强制 UTF-8。
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.getLevelName(level.upper()))

    # 访问日志由 RequestContextMiddleware 统一输出，关掉 uvicorn 自带的那份避免重复
    logging.getLogger("uvicorn.access").disabled = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

"""FastAPI 应用装配。

本文件只做装配：中间件、异常处理、路由挂载、生命周期。
业务逻辑一律放在 `app/modules/<域>/service.py` 中，这里不出现任何业务规则。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import api_router, root_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware
from app.db.session import dispose_engine

logger = get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """构造应用实例。测试可传入自定义 Settings 覆盖配置。"""
    cfg = settings or get_settings()
    configure_logging("DEBUG" if cfg.debug else "INFO")

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info("服务启动：env=%s 时区=%s", cfg.app_env, cfg.app_timezone)
        yield
        dispose_engine()
        logger.info("服务已停止")

    app = FastAPI(
        title=cfg.app_name,
        version=__version__,
        description="食堂健康管理系统后端接口：营养核算、采购预测与决策支持。",
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url=None,
        debug=cfg.debug,
        lifespan=lifespan,
    )

    app.add_middleware(RequestContextMiddleware)

    # 仅在显式配置了来源时启用 CORS：开发走 Vite 代理、生产走 nginx 反代，都是同源
    if cfg.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cfg.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    register_exception_handlers(app)

    app.include_router(root_router)
    app.include_router(api_router, prefix=cfg.api_prefix)

    return app


app = create_app()

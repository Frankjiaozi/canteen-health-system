"""系统域路由：健康检查。

这两个接口不挂在 /api/v1 下，供容器编排与运维直接探活。
"""

from __future__ import annotations

import time
from datetime import datetime

from fastapi import APIRouter, Depends, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import __version__
from app.core.config import get_settings
from app.core.errors import ServiceUnavailableError
from app.core.logging import get_logger
from app.db.session import get_session
from app.modules.system.schemas import DatabaseHealthResponse, HealthResponse

logger = get_logger(__name__)

router = APIRouter(tags=["系统"])


@router.get("/health", response_model=HealthResponse, summary="存活检查")
def health() -> HealthResponse:
    """进程存活即返回 200，不触达数据库。"""
    settings = get_settings()
    return HealthResponse(
        app_name=settings.app_name,
        version=__version__,
        env=settings.app_env,
        timezone=settings.app_timezone,
        server_time=datetime.now(settings.timezone),
    )


@router.get(
    "/health/db",
    response_model=DatabaseHealthResponse,
    summary="数据库连通性检查",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "数据库不可用"}},
)
def health_db(session: Session = Depends(get_session)) -> DatabaseHealthResponse:
    """真实往返一次查询；失败时返回结构化 503，而不是静默失败。"""
    started = time.perf_counter()
    try:
        raw_version = session.execute(text("select version()")).scalar_one()
    except SQLAlchemyError as exc:
        # 底层异常细节只进日志：响应里若带上连接串等信息会造成信息泄露
        logger.exception("数据库连通性检查失败")
        raise ServiceUnavailableError("数据库连接失败，请检查数据库是否已启动") from exc

    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    server_version = str(raw_version).split(" on ")[0]
    return DatabaseHealthResponse(server_version=server_version, latency_ms=latency_ms)

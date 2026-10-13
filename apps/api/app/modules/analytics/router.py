"""管理端看板接口。

需要登录：看板面向后勤与校方，展示的是群体级营养达成情况。三个可登录角色都能查看。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.modules.analytics import service
from app.modules.analytics.schemas import (
    ComplianceResponse,
    DashboardSummary,
    PerCapitaResponse,
    TrendsResponse,
    WasteResponse,
)
from app.modules.auth.dependencies import require_roles
from app.modules.auth.schemas import AuthUser
from app.shared.enums import UserRole

router = APIRouter(prefix="/dashboard", tags=["管理端看板"])

VIEW_ROLES = (UserRole.RECORDER, UserRole.CANTEEN_ADMIN, UserRole.SCHOOL_ADMIN)

#: 时间范围参数。切换它，各接口的结果与图表随之变化。
DaysQuery = Query(default=14, ge=1, le=90, description="统计最近多少天（含今天）")


@router.get("/summary", response_model=DashboardSummary, summary="关键指标汇总")
def read_summary(
    days: int = DaysQuery,
    session: Session = Depends(get_session),
    _: AuthUser = Depends(require_roles(*VIEW_ROLES)),
) -> DashboardSummary:
    return service.build_summary(session, days=days)


@router.get("/trends", response_model=TrendsResponse, summary="油盐糖用量趋势")
def read_trends(
    days: int = DaysQuery,
    session: Session = Depends(get_session),
    _: AuthUser = Depends(require_roles(*VIEW_ROLES)),
) -> TrendsResponse:
    return service.build_trends(session, days=days)


@router.get("/per-capita", response_model=PerCapitaResponse, summary="人均摄入与推荐值")
def read_per_capita(
    days: int = DaysQuery,
    session: Session = Depends(get_session),
    _: AuthUser = Depends(require_roles(*VIEW_ROLES)),
) -> PerCapitaResponse:
    return service.build_per_capita(session, days=days)


@router.get("/compliance", response_model=ComplianceResponse, summary="营养达标率")
def read_compliance(
    days: int = DaysQuery,
    session: Session = Depends(get_session),
    _: AuthUser = Depends(require_roles(*VIEW_ROLES)),
) -> ComplianceResponse:
    return service.build_compliance(session, days=days)


@router.get("/waste", response_model=WasteResponse, summary="剩餐量与浪费率")
def read_waste(
    days: int = DaysQuery,
    session: Session = Depends(get_session),
    _: AuthUser = Depends(require_roles(*VIEW_ROLES)),
) -> WasteResponse:
    return service.build_waste(session, days=days)

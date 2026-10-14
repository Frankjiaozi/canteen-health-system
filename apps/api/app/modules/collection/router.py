"""每日采集接口。

采集是整条链路的起点：录入员在这里填几个数字，营养结果随之重算，公开大屏就看到结果。
写操作只开放给能对数据负责的两个角色，学校管理方是只读的观察者。
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.modules.auth.dependencies import require_roles
from app.modules.auth.schemas import AuthUser
from app.modules.collection import service
from app.modules.collection.schemas import (
    DailyLogPage,
    DailyLogSaved,
    DailyLogSheet,
    DailyLogWrite,
)
from app.shared.enums import MealType, UserRole

router = APIRouter(prefix="/collection", tags=["每日采集"])

WRITE_ROLES = (UserRole.RECORDER, UserRole.CANTEEN_ADMIN)
VIEW_ROLES = (UserRole.RECORDER, UserRole.CANTEEN_ADMIN, UserRole.SCHOOL_ADMIN)


@router.get("/logs", response_model=DailyLogPage, summary="分页查询采集记录")
def list_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    start: date | None = Query(default=None, description="起始日期（含）"),
    end: date | None = Query(default=None, description="结束日期（含）"),
    session: Session = Depends(get_session),
    _: AuthUser = Depends(require_roles(*VIEW_ROLES)),
) -> DailyLogPage:
    return service.list_logs(session, page=page, page_size=page_size, start=start, end=end)


@router.get("/logs/{on_date}", response_model=DailyLogSheet, summary="取某天某一餐的采集单")
def get_sheet(
    on_date: date,
    meal_type: MealType = Query(default=MealType.LUNCH),
    session: Session = Depends(get_session),
    _: AuthUser = Depends(require_roles(*VIEW_ROLES)),
) -> DailyLogSheet:
    return service.build_sheet(session, on_date=on_date, meal_type=meal_type)


@router.put("/logs/{on_date}", response_model=DailyLogSaved, summary="保存采集单")
def save_sheet(
    on_date: date,
    payload: DailyLogWrite,
    session: Session = Depends(get_session),
    actor: AuthUser = Depends(require_roles(*WRITE_ROLES)),
) -> DailyLogSaved:
    return service.save_sheet(session, on_date=on_date, payload=payload, actor_id=actor.id)

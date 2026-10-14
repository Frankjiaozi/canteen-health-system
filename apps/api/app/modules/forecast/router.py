"""消耗量预测接口。

写成操作只开放给能对数据负责的两个角色：预测结果会直接影响采购量，
学校管理方看得到读结果，但不该替食堂下单。
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.modules.auth.dependencies import require_roles
from app.modules.auth.schemas import AuthUser
from app.modules.forecast import service
from app.modules.forecast.schemas import (
    BacktestResult,
    ForecastRunResult,
    HolidayPage,
    HolidayRead,
    HolidayWrite,
)
from app.shared.enums import MealType, UserRole

router = APIRouter(prefix="/forecast", tags=["消耗量预测"])

WRITE_ROLES = (UserRole.RECORDER, UserRole.CANTEEN_ADMIN)
VIEW_ROLES = (UserRole.RECORDER, UserRole.CANTEEN_ADMIN, UserRole.SCHOOL_ADMIN)


@router.post("/run", response_model=ForecastRunResult, summary="生成某天某一餐的份数预测")
def run_forecast(
    on_date: date = Query(description="要预测的日期"),
    meal_type: MealType = Query(default=MealType.LUNCH),
    session: Session = Depends(get_session),
    _: AuthUser = Depends(require_roles(*WRITE_ROLES)),
) -> ForecastRunResult:
    return service.run_forecast(session, on_date=on_date, meal_type=meal_type)


@router.get("/backtest", response_model=BacktestResult, summary="回测：与历史实际份数比 MAPE")
def backtest(
    days: int = Query(default=56, ge=7, le=180, description="回测天数"),
    meal_type: MealType = Query(default=MealType.LUNCH),
    session: Session = Depends(get_session),
    _: AuthUser = Depends(require_roles(*VIEW_ROLES)),
) -> BacktestResult:
    return service.backtest(session, days=days, meal_type=meal_type)


@router.get("/holidays", response_model=HolidayPage, summary="法定节假日日历")
def list_holidays(
    year: int = Query(default=2026, ge=2020, le=2100),
    session: Session = Depends(get_session),
    _: AuthUser = Depends(require_roles(*VIEW_ROLES)),
) -> HolidayPage:
    return service.list_holidays(session, year=year)


@router.patch("/holidays/{holiday_id}", response_model=HolidayRead, summary="核对与修正日历条目")
def update_holiday(
    holiday_id: UUID,
    payload: HolidayWrite,
    session: Session = Depends(get_session),
    _: AuthUser = Depends(require_roles(*WRITE_ROLES)),
) -> HolidayRead:
    return service.update_holiday(session, holiday_id=holiday_id, payload=payload)

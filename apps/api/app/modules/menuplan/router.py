"""「明日菜单与采购」接口。

一次调用把三件事算完：推荐选菜 → 预测份数 → 采购用料。
写成操作只开放给能对菜单与采购负责的两个角色。学校管理方看得到结果，
但定菜单、下采购单不是他的职责。
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from app.db.session import get_session
from app.modules.auth.dependencies import require_roles
from app.modules.auth.schemas import AuthUser
from app.modules.menuplan import service
from app.modules.menuplan.schemas import MenuPlanResponse, MenuPlanSyncResult
from app.shared.enums import MealType, UserRole
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

router = APIRouter(prefix="/menu-plan", tags=["明日菜单与采购"])

WRITE_ROLES = (UserRole.RECORDER, UserRole.CANTEEN_ADMIN)


@router.post("/generate", response_model=MenuPlanResponse, summary="生成明日菜单与采购建议")
def generate(
    on_date: date = Query(description="要安排的日期"),
    meal_type: MealType = Query(default=MealType.LUNCH),
    diner_count: int | None = Query(default=None, ge=1, description="不填则用最近一次采集的人次"),
    session: Session = Depends(get_session),
    _: AuthUser = Depends(require_roles(*WRITE_ROLES)),
) -> MenuPlanResponse:
    return service.build_menu_plan(
        session, on_date=on_date, meal_type=meal_type, diner_count=diner_count
    )


@router.post("/sync", response_model=MenuPlanSyncResult, summary="把这版菜单同步至当日数据")
def sync(
    on_date: date = Query(description="要写入的日期"),
    meal_type: MealType = Query(default=MealType.LUNCH),
    suggestion_id: UUID = Query(description="要同步的那一版菜单"),
    session: Session = Depends(get_session),
    actor: AuthUser = Depends(require_roles(*WRITE_ROLES)),
) -> MenuPlanSyncResult:
    return service.sync_to_day(
        session,
        on_date=on_date,
        meal_type=meal_type,
        suggestion_id=suggestion_id,
        actor_id=actor.id,
    )

"""「明日菜单与采购」接口。

一次调用把三件事算完：推荐选菜 → 预测份数 → 采购用料。
写成操作只开放给能对菜单与采购负责的两个角色。学校管理方看得到结果，
但定菜单、下采购单不是他的职责。
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from app.core.errors import ConflictError
from app.db.session import get_session
from app.modules.auth.dependencies import require_roles
from app.modules.auth.schemas import AuthUser
from app.modules.menuplan import publication, readiness, service
from app.modules.menuplan.schemas import (
    MenuPlanConstraints,
    MenuPlanResponse,
    PlanReadiness,
    PublishPlanReceipt,
    PublishPlanRequest,
)
from app.shared.enums import MealType, UserRole
from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

router = APIRouter(prefix="/menu-plan", tags=["明日菜单与采购"])

WRITE_ROLES = (UserRole.RECORDER, UserRole.CANTEEN_ADMIN)


@router.get("/readiness", response_model=PlanReadiness, summary="只读检查计划所需数据")
def inspect_readiness(
    on_date: date,
    meal_type: MealType = MealType.LUNCH,
    excluded_dish_ids: list[UUID] = Query(default=[], max_length=50),
    session: Session = Depends(get_session),
    _: AuthUser = Depends(require_roles(*WRITE_ROLES, UserRole.SCHOOL_ADMIN)),
) -> PlanReadiness:
    return readiness.inspect(
        session,
        on_date=on_date,
        meal_type=meal_type,
        excluded_dish_ids=frozenset(excluded_dish_ids),
    )


@router.post("/generate", response_model=MenuPlanResponse, summary="生成明日菜单与采购建议")
def generate(
    on_date: date = Query(description="要安排的日期"),
    meal_type: MealType = Query(default=MealType.LUNCH),
    diner_count: int | None = Query(default=None, ge=1, description="不填则用最近一次采集的人次"),
    constraints: MenuPlanConstraints | None = Body(default=None),
    session: Session = Depends(get_session),
    _: AuthUser = Depends(require_roles(*WRITE_ROLES)),
) -> MenuPlanResponse:
    return service.build_menu_plan(
        session,
        on_date=on_date,
        meal_type=meal_type,
        diner_count=diner_count,
        excluded_dish_ids=frozenset(constraints.excluded_dish_ids) if constraints else frozenset(),
        budget_per_person=constraints.budget_per_person if constraints else None,
    )


@router.post(
    "/{suggestion_id}/publish", response_model=PublishPlanReceipt, summary="确认并发布计算快照"
)
def publish(
    suggestion_id: UUID,
    payload: PublishPlanRequest,
    session: Session = Depends(get_session),
    actor: AuthUser = Depends(require_roles(*WRITE_ROLES)),
) -> PublishPlanReceipt:
    try:
        return publication.publish(
            session, suggestion_id=suggestion_id, payload=payload, actor=actor
        )
    except DBAPIError as exc:
        session.rollback()
        if getattr(exc.orig, "sqlstate", None) in {"40P01", "55P03", "40001", "23505"}:
            raise ConflictError("菜单或配方正在被其他操作更新，请刷新后重试") from exc
        raise

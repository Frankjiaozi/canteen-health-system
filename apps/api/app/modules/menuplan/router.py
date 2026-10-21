"""「明日菜单与采购」接口。

一次调用把三件事算完：推荐选菜 → 预测份数 → 采购用料。
写成操作只开放给能对菜单与采购负责的两个角色。学校管理方看得到结果，
但定菜单、下采购单不是他的职责。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from app.core.errors import ConflictError
from app.db.session import get_session
from app.modules.auth.dependencies import require_roles
from app.modules.auth.schemas import AuthUser
from app.modules.menuplan import publication, readiness, service
from app.modules.menuplan.schemas import (
    DailyMenuPlanResponse,
    MenuPlanBatchResult,
    MenuPlanBatchSyncRequest,
    MenuPlanConstraints,
    MenuPlanHistoryItem,
    MenuPlanResponse,
    MenuPlanSyncResult,
    PlanReadiness,
    PublishPlanReceipt,
    PublishPlanRequest,
    UndoPlanReceipt,
)
from app.shared.enums import MealType, UserRole
from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

router = APIRouter(prefix="/menu-plan", tags=["明日菜单与采购"])

WRITE_ROLES = (UserRole.RECORDER, UserRole.CANTEEN_ADMIN)


@router.get(
    "/history", response_model=list[MenuPlanHistoryItem], summary="读取已保存的菜单与采购快照"
)
def history(
    on_date: date,
    session: Session = Depends(get_session),
    _: AuthUser = Depends(require_roles(*WRITE_ROLES, UserRole.SCHOOL_ADMIN)),
) -> list[MenuPlanHistoryItem]:
    return service.read_history(session, on_date=on_date)


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
    diner_count: int | None = Query(
        default=None, ge=1, description="不填时由系统按同星期历史与日历预测"
    ),
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
    "/generate-day",
    response_model=DailyMenuPlanResponse,
    summary="一键生成早中晚三餐与合并采购单",
)
def generate_day(
    on_date: date = Query(description="要安排的日期"),
    budget_per_person: Decimal | None = Query(
        default=None, gt=0, le=1000, max_digits=8, decimal_places=2
    ),
    excluded_dish_ids: list[UUID] = Query(default=[], max_length=50),
    session: Session = Depends(get_session),
    _: AuthUser = Depends(require_roles(*WRITE_ROLES)),
) -> DailyMenuPlanResponse:
    return service.build_daily_plan(
        session,
        on_date=on_date,
        budget_per_person=budget_per_person,
        excluded_dish_ids=frozenset(excluded_dish_ids),
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


@router.post(
    "/{suggestion_id}/undo", response_model=UndoPlanReceipt, summary="撤回一次已发布的方案"
)
def undo(
    suggestion_id: UUID,
    session: Session = Depends(get_session),
    actor: AuthUser = Depends(require_roles(*WRITE_ROLES)),
) -> UndoPlanReceipt:
    """把菜单恢复成发布前的样子，方案回到待确认。

    发布之后这餐菜单被别人改过、或者已经录了采集，都会拒绝——撤回不能覆盖别人的改动，
    也不能拿计划盖掉实际供应。
    """
    try:
        return publication.undo_publish(session, suggestion_id=suggestion_id, actor=actor)
    except DBAPIError as exc:
        session.rollback()
        if getattr(exc.orig, "sqlstate", None) in {"40P01", "55P03", "40001", "23505"}:
            raise ConflictError("菜单正在被其他操作更新，请刷新后重试") from exc
        raise


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


@router.post("/batch/generate", response_model=MenuPlanBatchResult, summary="按日期区间批量排菜单")
def batch_generate(
    start_date: date = Query(description="开始日期"),
    end_date: date = Query(description="结束日期（含）"),
    meal_type: MealType = Query(default=MealType.LUNCH),
    session: Session = Depends(get_session),
    _: AuthUser = Depends(require_roles(*WRITE_ROLES)),
) -> MenuPlanBatchResult:
    return service.generate_batch(
        session, start_date=start_date, end_date=end_date, meal_type=meal_type
    )


@router.post("/batch/sync", response_model=MenuPlanBatchResult, summary="一键导入这几天的当日菜单")
def batch_sync(
    payload: MenuPlanBatchSyncRequest,
    start_date: date = Query(description="开始日期"),
    end_date: date = Query(description="结束日期（含）"),
    meal_type: MealType = Query(default=MealType.LUNCH),
    session: Session = Depends(get_session),
    actor: AuthUser = Depends(require_roles(*WRITE_ROLES)),
) -> MenuPlanBatchResult:
    return service.sync_batch(
        session,
        start_date=start_date,
        end_date=end_date,
        meal_type=meal_type,
        actor_id=actor.id,
        suggestion_ids=payload.suggestion_ids,
    )

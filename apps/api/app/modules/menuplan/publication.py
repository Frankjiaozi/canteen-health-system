"""菜单快照与发布边界。Agent 只能提交快照凭据，不能提交任意菜单明细。"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.core.config import get_settings
from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.modules.audit.models import AuditLog
from app.modules.auth.schemas import AuthUser
from app.modules.collection.models import DailyLog
from app.modules.dish.models import Dish, RecipeItem, RecipeSeasoning
from app.modules.ingredient.models import Ingredient
from app.modules.menu.locking import lock_meal
from app.modules.menu.models import MenuDay, MenuDayItem
from app.modules.menuplan.schemas import MenuPlanResponse, PublishPlanReceipt, PublishPlanRequest
from app.modules.nutrition import service as nutrition_service
from app.modules.recommendation.models import MenuSuggestion
from app.modules.seasoning.models import Seasoning
from app.shared.enums import AuditAction, SuggestionStatus
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

CALCULATION_VERSION = "menu-plan-20261016.2"


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()


def catalog_tokens(session: Session, dish_ids: list[UUID], *, lock: bool = False) -> dict[str, str]:
    """生成与发布时核对配方、原料营养和单价，避免拿旧采购数字确认新配方。"""

    def load(model: Any, condition: Any) -> list[Any]:
        statement = (
            select(model)
            .where(condition)
            .order_by(model.id)
            .execution_options(populate_existing=True)
        )
        if lock:
            statement = statement.with_for_update(read=True)
        return list(session.scalars(statement).all())

    dishes = load(Dish, Dish.id.in_(dish_ids))
    items = load(RecipeItem, RecipeItem.dish_id.in_(dish_ids))
    seasonings = load(RecipeSeasoning, RecipeSeasoning.dish_id.in_(dish_ids))
    ingredients = {
        row.id: row
        for row in load(Ingredient, Ingredient.id.in_({row.ingredient_id for row in items}))
    }
    flavors = {
        row.id: row
        for row in load(Seasoning, Seasoning.id.in_({row.seasoning_id for row in seasonings}))
    }

    def record(row: Any) -> dict[str, str]:
        return {column.name: str(getattr(row, column.name)) for column in row.__table__.columns}

    return {
        str(dish.id): digest(
            {
                "dish": record(dish),
                "ingredients": sorted(
                    [
                        (str(row.id), record(row), record(ingredients[row.ingredient_id]))
                        for row in items
                        if row.dish_id == dish.id
                    ],
                    key=lambda value: str(value[0]),
                ),
                "seasonings": sorted(
                    [
                        (str(row.id), record(row), record(flavors[row.seasoning_id]))
                        for row in seasonings
                        if row.dish_id == dish.id
                    ],
                    key=lambda value: str(value[0]),
                ),
            }
        )
        for dish in dishes
    }


def menu_state(session: Session, suggestion: MenuSuggestion) -> dict[str, Any]:
    menu = session.scalar(
        select(MenuDay).where(
            MenuDay.date == suggestion.date, MenuDay.meal_type == suggestion.meal_type
        )
    )
    if menu is None:
        return {"menu": None}
    items = session.scalars(select(MenuDayItem).where(MenuDayItem.menu_day_id == menu.id)).all()
    return {
        "id": str(menu.id),
        "updated_at": str(menu.updated_at),
        "note": menu.note,
        "items": sorted(
            (str(row.dish_id), str(row.planned_servings), str(row.updated_at), row.is_substituted)
            for row in items
        ),
    }


def save_snapshot(
    session: Session, plan: MenuPlanResponse, catalog_before: dict[str, str]
) -> MenuPlanResponse:
    suggestion = session.get(MenuSuggestion, UUID(plan.suggestion_id))
    if suggestion is None:
        raise NotFoundError("推荐不存在")
    plan.expected_menu_token = digest(menu_state(session, suggestion))
    ids = [UUID(row.dish_id) for row in plan.dishes]
    current_catalog = catalog_tokens(session, ids, lock=True)
    if current_catalog != {str(item): catalog_before.get(str(item)) for item in ids}:
        raise ConflictError("计算期间配方或原料数据发生变化，请重新生成方案")
    versions = {
        str(row.id): row.recipe_version
        for row in session.scalars(select(Dish).where(Dish.id.in_(ids))).all()
    }
    # 凭据包含配方版本与全部采购结果，任何快照修改都会让凭据失效。
    snapshot = {
        "plan": plan.model_dump(mode="json"),
        "recipe_versions": versions,
        "catalog_tokens": current_catalog,
    }
    plan.snapshot_token = digest(snapshot)
    snapshot["plan"] = plan.model_dump(mode="json")
    suggestion.nutrition_gap = {**suggestion.nutrition_gap, "menu_plan_snapshot": snapshot}
    session.commit()
    return plan


def publish(
    session: Session, *, suggestion_id: UUID, payload: PublishPlanRequest, actor: AuthUser
) -> PublishPlanReceipt:
    suggestion = session.scalar(
        select(MenuSuggestion).where(MenuSuggestion.id == suggestion_id).with_for_update()
    )
    if suggestion is None:
        raise NotFoundError("推荐不存在")
    stored = suggestion.nutrition_gap or {}
    snapshot = stored.get("menu_plan_snapshot")
    if not snapshot:
        raise ConflictError("这份旧建议没有完整计算快照，请重新生成后确认")
    plan = MenuPlanResponse.model_validate(snapshot["plan"])
    unsigned = {**snapshot, "plan": {**snapshot["plan"], "snapshot_token": ""}}
    if payload.snapshot_token != plan.snapshot_token or digest(unsigned) != plan.snapshot_token:
        raise ConflictError("方案快照不匹配，请刷新方案后重试")
    if payload.expected_menu_token != plan.expected_menu_token:
        raise ConflictError("菜单版本凭据不匹配")
    receipt = stored.get("publication")
    if receipt:
        return PublishPlanReceipt(**{**receipt, "already_published": True})
    if plan.calculation_version != CALCULATION_VERSION:
        raise ConflictError("计算规则已更新，请重新生成并核对后发布；旧方案仍保留供比较")
    if suggestion.status == SuggestionStatus.REJECTED:
        raise ConflictError("这份建议已被否决，请重新生成")

    # 同一日期/餐次串行发布，包括尚未有 menu_day 行的情况。
    lock_meal(session, suggestion.date, suggestion.meal_type)
    menu = session.scalar(
        select(MenuDay)
        .where(MenuDay.date == suggestion.date, MenuDay.meal_type == suggestion.meal_type)
        .with_for_update()
    )
    before = menu_state(session, suggestion)
    if digest(before) != payload.expected_menu_token:
        raise ConflictError("这餐菜单已被其他人修改，请重新生成并核对后再发布")
    if session.scalar(
        select(DailyLog.id).where(
            DailyLog.date == suggestion.date, DailyLog.meal_type == suggestion.meal_type
        )
    ):
        raise ConflictError("这餐已有实际采集记录，不能用计划覆盖实际供应")
    today = datetime.now(get_settings().timezone).date()
    if suggestion.date < today:
        raise BusinessRuleError("不能发布过去日期的计划")
    ids = [UUID(row.dish_id) for row in plan.dishes]
    if catalog_tokens(session, ids, lock=True) != snapshot.get("catalog_tokens"):
        raise ConflictError("配方、原料营养或单价已经变化，请重新生成并核对后发布")
    if plan.total_cost is not None and Decimal(plan.total_cost) > Decimal(plan.budget):
        raise BusinessRuleError("采购金额超出本次预算，请调整条件后重新生成")
    dishes = list(session.scalars(select(Dish).where(Dish.id.in_(ids))).all())
    if len(dishes) != len(ids) or any(
        not row.is_active or row.recipe_version != snapshot["recipe_versions"].get(str(row.id))
        for row in dishes
    ):
        raise ConflictError("菜品或配方已经变化，请重新计算采购与营养后再发布")
    if menu is None:
        menu = MenuDay(date=suggestion.date, meal_type=suggestion.meal_type, created_by=actor.id)
        session.add(menu)
        session.flush()
    session.execute(delete(MenuDayItem).where(MenuDayItem.menu_day_id == menu.id))
    for row in plan.dishes:
        quantity = row.planned_servings or row.predicted_servings or str(plan.diner_count)
        session.add(
            MenuDayItem(
                menu_day_id=menu.id,
                dish_id=UUID(row.dish_id),
                planned_servings=Decimal(quantity),
            )
        )
    menu.note = f"确认发布方案 {suggestion.id}；采购金额以生成时快照为准"
    suggestion.status = SuggestionStatus.ACCEPTED
    suggestion.decided_by = actor.id
    suggestion.decided_at = datetime.now(get_settings().timezone)
    result = PublishPlanReceipt(
        suggestion_id=str(suggestion.id),
        menu_day_id=str(menu.id),
        on_date=suggestion.date,
        meal_type=suggestion.meal_type,
        dish_count=len(plan.dishes),
        published_at=suggestion.decided_at.isoformat(),
        published_by=actor.display_name,
    )
    suggestion.nutrition_gap = {**stored, "publication": result.model_dump(mode="json")}
    session.add(
        AuditLog(
            entity_type="menu_day",
            entity_id=str(menu.id),
            action=AuditAction.APPROVE,
            actor_id=actor.id,
            actor_name=actor.display_name,
            before=before,
            after={
                "suggestion_id": str(suggestion.id),
                "snapshot_token": plan.snapshot_token,
                "dishes": [row.model_dump(mode="json") for row in plan.dishes],
            },
            note="从计算快照确认发布菜单；未创建实际用量记录",
        )
    )
    session.flush()
    nutrition_service.compute_menu_day(
        session, on_date=suggestion.date, meal_type=suggestion.meal_type
    )
    session.commit()
    return result

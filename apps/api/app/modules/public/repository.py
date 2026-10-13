"""公开大屏的数据访问。

与营养域一样，这里是**只读**的跨域装配：大屏天然要横向读取菜单、菜品、营养结果、
每日记录与膳食基准。写入一律走各域自己的 service。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.collection.models import DailyLog
from app.modules.dish.models import Dish, RecipeItem
from app.modules.menu.models import MenuDay, MenuDayItem
from app.modules.nutrition.models import DishNutrition, NutritionStandard
from app.shared.enums import MealType, NutrientCaliber, NutritionValueType


def load_menu_day(session: Session, on_date: date) -> MenuDay | None:
    """取当天的主餐次菜单。

    展示按餐次优先：午餐 → 晚餐 → 早餐。演示场景与多数学校都以午餐为主。
    """
    menu_days = list(session.scalars(select(MenuDay).where(MenuDay.date == on_date)).all())
    if not menu_days:
        return None

    priority = {MealType.LUNCH: 0, MealType.DINNER: 1, MealType.BREAKFAST: 2}
    return min(menu_days, key=lambda item: priority[item.meal_type])


def load_dishes(session: Session, menu_day_id: UUID) -> list[Dish]:
    return list(
        session.scalars(
            select(Dish)
            .join(MenuDayItem, MenuDayItem.dish_id == Dish.id)
            .where(MenuDayItem.menu_day_id == menu_day_id)
            .order_by(Dish.category, Dish.name)
        ).all()
    )


def load_per_serving_nutritions(
    session: Session, *, dish_ids: Sequence[UUID], on_date: date
) -> dict[UUID, DishNutrition]:
    if not dish_ids:
        return {}
    rows = session.scalars(
        select(DishNutrition).where(
            DishNutrition.dish_id.in_(dish_ids),
            DishNutrition.date == on_date,
            DishNutrition.caliber == NutrientCaliber.PER_SERVING,
            DishNutrition.value_type == NutritionValueType.THEORETICAL,
        )
    ).all()
    return {row.dish_id: row for row in rows}


def load_daily_logs(session: Session, on_date: date) -> list[DailyLog]:
    return list(session.scalars(select(DailyLog).where(DailyLog.date == on_date)).all())


def count_day_ingredients(session: Session, *, on_date: date) -> int:
    """当日供应菜品用到的食材种类数（对应指南的「食物多样」）。"""
    total = session.scalar(
        select(func.count(func.distinct(RecipeItem.ingredient_id)))
        .select_from(RecipeItem)
        .join(MenuDayItem, MenuDayItem.dish_id == RecipeItem.dish_id)
        .join(MenuDay, MenuDay.id == MenuDayItem.menu_day_id)
        .where(MenuDay.date == on_date)
    )
    return int(total or 0)


def load_active_standards(session: Session) -> list[NutritionStandard]:
    return list(
        session.scalars(
            select(NutritionStandard)
            .where(NutritionStandard.is_active.is_(True))
            .order_by(NutritionStandard.code)
        ).all()
    )

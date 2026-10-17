"""推荐域的数据访问。

只读的跨域装配：推荐要把菜品、配方、单价、历史受欢迎度与膳食基准拼成求解器的输入。
写入只落在 `menu_suggestions` 表上。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError
from app.modules.collection.models import DailyLog, DailyLogItem
from app.modules.dish.models import Dish, RecipeItem, RecipeSeasoning
from app.modules.ingredient.models import Ingredient
from app.modules.menu.models import MenuDay, MenuDayItem
from app.modules.nutrition.models import NutritionStandard
from app.modules.recommendation.models import MenuSuggestion
from app.modules.seasoning.models import Seasoning
from app.shared.enums import AnomalyFlag, MealType, SeasoningCategory

#: 与膳食基准直接对应的三类调料
KEY_SEASONINGS: tuple[SeasoningCategory, ...] = (
    SeasoningCategory.EDIBLE_OIL,
    SeasoningCategory.SALT,
    SeasoningCategory.SUGAR,
)


@dataclass
class MaterialUsage:
    """一道菜的用料账：成本、三类调料用量、涉及的食材。"""

    cost_per_serving: Decimal = Decimal("0")
    #: 单价缺失时按 0 计入成本，但要记下来——成本因此会偏低，不能闷着不说
    missing_price: bool = False
    seasoning_g: dict[SeasoningCategory, Decimal] = field(default_factory=dict)
    ingredient_ids: set[UUID] = field(default_factory=set)
    ingredient_names: list[str] = field(default_factory=list)


def load_materials(session: Session) -> dict[UUID, MaterialUsage]:
    """每道菜的单份用料账。

    单价是「元 / 公斤**市品**」，配方用量也是市品重量（克），因此算钱时直接除以 1000——
    **不乘可食部比例**。可食部只影响营养计算（吃进去的那部分），不影响买菜花的钱。
    """
    usage: dict[UUID, MaterialUsage] = {}

    rows = session.execute(
        select(
            RecipeItem.dish_id,
            Ingredient.id,
            Ingredient.name,
            Ingredient.unit_price,
            RecipeItem.quantity_per_serving_g,
        ).join(Ingredient, Ingredient.id == RecipeItem.ingredient_id)
    ).all()
    for dish_id, ingredient_id, name, price, quantity in rows:
        entry = usage.setdefault(dish_id, MaterialUsage())
        entry.ingredient_ids.add(ingredient_id)
        entry.ingredient_names.append(name)
        if price is None:
            entry.missing_price = True
        else:
            entry.cost_per_serving += Decimal(quantity) / Decimal("1000") * Decimal(price)

    seasoning_rows = session.execute(
        select(
            RecipeSeasoning.dish_id,
            Seasoning.category,
            Seasoning.unit_price,
            RecipeSeasoning.quantity_per_serving_g,
        ).join(Seasoning, Seasoning.id == RecipeSeasoning.seasoning_id)
    ).all()
    for dish_id, category, price, quantity in seasoning_rows:
        entry = usage.setdefault(dish_id, MaterialUsage())
        amount = Decimal(quantity)
        if price is None:
            entry.missing_price = True
        else:
            entry.cost_per_serving += amount / Decimal("1000") * Decimal(price)
        if category in KEY_SEASONINGS:
            entry.seasoning_g[category] = entry.seasoning_g.get(category, Decimal("0")) + amount

    return usage


def load_active_dishes(session: Session) -> dict[UUID, Dish]:
    return {
        dish.id: dish
        for dish in session.scalars(select(Dish).where(Dish.is_active.is_(True))).all()
    }


def load_popularity(
    session: Session, *, on_date: date | None = None, meal_type: MealType | None = None
) -> dict[UUID, tuple[Decimal, int]]:
    """历史受欢迎度：每道菜的平均出餐份数与出现次数。

    用**平均**而不是总和：上过多少次菜单不该等价于受欢迎，
    轮换里排得多的菜本来就多。异常日不计入——临时接待那天的份数不代表口味。
    """
    statement = (
        select(
            DailyLogItem.dish_id,
            func.avg(DailyLogItem.servings_produced),
            func.count(),
        )
        .join(DailyLog, DailyLog.id == DailyLogItem.daily_log_id)
        .where(
            DailyLogItem.servings_produced > 0,
            ~DailyLog.anomaly_flags.contains([AnomalyFlag.RECEPTION.value]),
        )
        .group_by(DailyLogItem.dish_id)
    )
    if on_date is not None:
        statement = statement.where(DailyLog.date < on_date)
    if meal_type is not None:
        statement = statement.where(DailyLog.meal_type == meal_type)
    rows = session.execute(statement).all()
    return {
        dish_id: (Decimal(str(average)), int(count))
        for dish_id, average, count in rows
        if average is not None
    }


def load_previous_dishes(session: Session, *, on_date: date, meal_type: MealType) -> set[UUID]:
    """前一天同一餐供应过的菜，用于「同一道菜不连续两日重复」。"""
    menu_day = session.scalar(
        select(MenuDay).where(
            MenuDay.date == on_date - timedelta(days=1), MenuDay.meal_type == meal_type
        )
    )
    if menu_day is None:
        return set()
    return set(
        session.scalars(select(MenuDayItem.dish_id).where(MenuDayItem.menu_day_id == menu_day.id))
    )


def load_standards(session: Session) -> list[NutritionStandard]:
    return list(
        session.scalars(
            select(NutritionStandard)
            .where(NutritionStandard.is_active.is_(True))
            .order_by(NutritionStandard.code)
        ).all()
    )


def load_latest_diner_count(
    session: Session, *, on_date: date, meal_type: MealType = MealType.LUNCH
) -> int:
    """最近一次采集里的就餐人次。

    人次只影响「人均供给」的折算，不影响选哪些菜；用最近一次实际值比用拍脑袋的常数好。
    """
    value = session.scalar(
        select(DailyLog.diner_count)
        .where(DailyLog.date < on_date, DailyLog.meal_type == meal_type, DailyLog.diner_count > 0)
        .order_by(DailyLog.date.desc())
        .limit(1)
    )
    if value is None:
        raise BusinessRuleError(
            f"供餐日期之前还没有{meal_type.label}的有效人次记录；请先补录历史，或在生成时直接指定人次"
        )
    return int(value)


def save_suggestion(
    session: Session,
    *,
    on_date: date,
    meal_type: MealType,
    candidate_menu: list[dict[str, object]],
    nutrition_gap: dict[str, object],
    cost_estimate: Decimal,
    reasons: list[dict[str, object]],
) -> MenuSuggestion:
    suggestion = MenuSuggestion(
        date=on_date,
        meal_type=meal_type,
        candidate_menu=candidate_menu,
        nutrition_gap=nutrition_gap,
        cost_estimate=cost_estimate,
        reasons=reasons,
    )
    session.add(suggestion)
    session.flush()
    return suggestion


def get_suggestion(session: Session, suggestion_id: UUID) -> MenuSuggestion | None:
    return session.get(MenuSuggestion, suggestion_id)


def list_suggestions(session: Session, *, on_date: date | None, limit: int) -> list[MenuSuggestion]:
    statement = select(MenuSuggestion)
    if on_date is not None:
        statement = statement.where(MenuSuggestion.date == on_date)
    return list(
        session.scalars(statement.order_by(MenuSuggestion.created_at.desc()).limit(limit)).all()
    )

"""看板域的数据访问。

与营养域、公开域一样，这里是**只读**的跨域聚合。看板天然要把每日记录、出品明细、
营养结果与基准拼在一起看；写入一律走各域自己的 service。
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.collection.models import DailyLog, DailyLogItem
from app.modules.dish.models import Dish, RecipeItem
from app.modules.menu.models import MenuDay, MenuDayItem
from app.modules.nutrition.models import DishNutrition, NutritionStandard
from app.shared.enums import NutrientCaliber
from app.shared.nutrients import NUTRIENT_FIELDS
from app.shared.nutrition_values import VALUE_TYPES, priority_expression


def load_daily_logs(session: Session, *, start: date, end: date) -> list[DailyLog]:
    return list(
        session.scalars(
            select(DailyLog)
            .where(DailyLog.date >= start, DailyLog.date <= end)
            .order_by(DailyLog.date, DailyLog.meal_type)
        ).all()
    )


def load_menu_days(session: Session, *, start: date, end: date) -> list[MenuDay]:
    return list(
        session.scalars(
            select(MenuDay)
            .where(MenuDay.date >= start, MenuDay.date <= end)
            .order_by(MenuDay.date, MenuDay.meal_type)
        ).all()
    )


def load_menu_items(
    session: Session, menu_day_ids: list[UUID]
) -> dict[UUID, list[tuple[Dish, MenuDayItem]]]:
    """菜单日里的菜与计划份数，按菜单日分组。"""
    if not menu_day_ids:
        return {}
    rows = session.execute(
        select(MenuDayItem, Dish)
        .join(Dish, Dish.id == MenuDayItem.dish_id)
        .where(MenuDayItem.menu_day_id.in_(menu_day_ids))
        .order_by(MenuDayItem.menu_day_id, Dish.category, Dish.name)
    ).all()
    grouped: dict[UUID, list[tuple[Dish, MenuDayItem]]] = {}
    for item, dish in rows:
        grouped.setdefault(item.menu_day_id, []).append((dish, item))
    return grouped


def load_waste_rows(
    session: Session, *, start: date, end: date
) -> list[tuple[date, int, str | None]]:
    """按天汇总出品重量与剩餐重量。

    出品重量由「出餐份数 × 该菜标准份量」推算，剩餐重量取明细里记录的实测值。
    """
    rows = session.execute(
        select(
            DailyLog.date,
            func.sum(DailyLogItem.servings_produced * Dish.standard_serving_g),
            func.sum(DailyLogItem.leftover_weight_g),
        )
        .select_from(DailyLogItem)
        .join(DailyLog, DailyLog.id == DailyLogItem.daily_log_id)
        .join(Dish, Dish.id == DailyLogItem.dish_id)
        .where(DailyLog.date >= start, DailyLog.date <= end)
        .group_by(DailyLog.date)
        .order_by(DailyLog.date)
    ).all()
    return [(row[0], int(row[1] or 0), None if row[2] is None else str(row[2])) for row in rows]


def load_day_per_capita_totals(
    session: Session, *, start: date, end: date
) -> dict[date, dict[str, str]]:
    """按天汇总人均口径的五项营养。

    当日人均摄入 = 当天各道菜人均口径结果之和。单份口径不参与这里，
    两个口径混用会得出完全错误的结论。

    每道菜同一天可能同时有理论、校准、抽样三份人均结果。**必须先按菜品各取一份
    再相加**：三份都加进去等于把同一道菜算三遍，人均摄入会凭空翻两三倍。
    取舍顺序与公开大屏一致（抽样 > 校准 > 理论），见 app.shared.nutrition_values。

    分区键必须带上餐次：一道菜午餐、晚餐都供应时是两条独立的结果，按「菜品 + 日期」
    分区会把晚餐那一条挤掉，等于漏算一餐。
    """
    best = (
        select(
            DishNutrition.date.label("date"),
            *[getattr(DishNutrition, field).label(field) for field in NUTRIENT_FIELDS],
            func.row_number()
            .over(
                partition_by=(
                    DishNutrition.dish_id,
                    DishNutrition.date,
                    DishNutrition.meal_type,
                ),
                order_by=priority_expression(DishNutrition.value_type),
            )
            .label("rank"),
        )
        .where(
            DishNutrition.date >= start,
            DishNutrition.date <= end,
            DishNutrition.caliber == NutrientCaliber.PER_CAPITA,
            DishNutrition.value_type.in_(VALUE_TYPES),
        )
        .subquery()
    )

    rows = session.execute(
        select(
            best.c.date,
            *[func.sum(getattr(best.c, field)).label(field) for field in NUTRIENT_FIELDS],
        )
        .where(best.c.rank == 1)
        .group_by(best.c.date)
        .order_by(best.c.date)
    ).all()

    return {
        row.date: {field: str(getattr(row, field)) for field in NUTRIENT_FIELDS} for row in rows
    }


def load_day_ingredient_counts(session: Session, *, start: date, end: date) -> dict[date, int]:
    rows = session.execute(
        select(MenuDay.date, func.count(func.distinct(RecipeItem.ingredient_id)))
        .select_from(MenuDay)
        .join(MenuDayItem, MenuDayItem.menu_day_id == MenuDay.id)
        .join(RecipeItem, RecipeItem.dish_id == MenuDayItem.dish_id)
        .where(MenuDay.date >= start, MenuDay.date <= end)
        .group_by(MenuDay.date)
    ).all()
    return {row[0]: int(row[1] or 0) for row in rows}


def load_active_standards(session: Session) -> list[NutritionStandard]:
    return list(
        session.scalars(
            select(NutritionStandard)
            .where(NutritionStandard.is_active.is_(True))
            .order_by(NutritionStandard.code)
        ).all()
    )

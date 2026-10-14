"""预测域的数据访问。

与营养域一样，这里是**只读的跨域装配**：预测天然要横向读取菜品、菜单、每日记录、
配方与食材，把它们拼成算法需要的形状。边界同样清楚——本模块不修改别的域的数据，
写入只落在 `forecasts` 表上。
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.modules.collection.models import DailyLog, DailyLogItem
from app.modules.dish.models import Dish, RecipeItem, RecipeSeasoning
from app.modules.forecast.models import Forecast, Holiday
from app.modules.ingredient.models import Ingredient
from app.modules.menu.models import MenuDay, MenuDayItem
from app.modules.seasoning.models import Seasoning
from app.shared.enums import HolidayKind, MealType


def load_holidays(session: Session, *, start: date, end: date) -> dict[date, HolidayKind]:
    rows = session.scalars(select(Holiday).where(Holiday.date >= start, Holiday.date <= end)).all()
    return {row.date: row.kind for row in rows}


def load_holiday_rows(session: Session, *, year: int) -> list[Holiday]:
    return list(
        session.scalars(
            select(Holiday)
            .where(Holiday.date >= date(year, 1, 1), Holiday.date <= date(year, 12, 31))
            .order_by(Holiday.date)
        ).all()
    )


def load_holiday(session: Session, *, day: date) -> Holiday | None:
    return session.scalar(select(Holiday).where(Holiday.date == day))


def load_dish_history(
    session: Session, *, start: date, end: date
) -> dict[UUID, list[tuple[date, Decimal]]]:
    """每道菜在区间内的出餐份数，**已经剔除不该进历史序列的日子**。

    三类日子要排除，否则它们会把移动平均带偏：

    1. 采集时标了异常的日子（临时接待、菜品停供、设备故障）；
    2. 菜单上标了临时替换的日子——实际供应的不是计划的那道菜；
    3. 出餐份数为 0 的记录（停供当天常会留一条 0）。
    """
    # 临时替换的 (菜, 日期) 单独取一次：把它写成 join 条件会变成一条既难读、
    # 又容易写错关联关系的语句，而这里的数据量小到根本不值得省这一次查询。
    substituted = {
        (dish_id, day)
        for dish_id, day in session.execute(
            select(MenuDayItem.dish_id, MenuDay.date)
            .join(MenuDay, MenuDay.id == MenuDayItem.menu_day_id)
            .where(
                MenuDay.date >= start,
                MenuDay.date <= end,
                MenuDayItem.is_substituted.is_(True),
            )
        ).all()
    }

    rows = session.execute(
        select(
            DailyLogItem.dish_id,
            DailyLog.date,
            DailyLogItem.servings_produced,
            DailyLog.anomaly_flags,
        )
        .join(DailyLog, DailyLog.id == DailyLogItem.daily_log_id)
        .where(DailyLog.date >= start, DailyLog.date <= end)
    ).all()

    history: dict[UUID, list[tuple[date, Decimal]]] = defaultdict(list)
    for dish_id, day, servings, flags in rows:
        if flags or (dish_id, day) in substituted:
            continue
        if servings is None or servings <= 0:
            continue
        history[dish_id].append((day, Decimal(servings)))
    return dict(history)


def load_active_dishes(session: Session) -> dict[UUID, Dish]:
    return {
        dish.id: dish
        for dish in session.scalars(select(Dish).where(Dish.is_active.is_(True))).all()
    }


def load_menu_day(session: Session, *, on_date: date, meal_type: MealType) -> MenuDay | None:
    return session.scalar(
        select(MenuDay).where(MenuDay.date == on_date, MenuDay.meal_type == meal_type)
    )


def load_menu_dish_ids(session: Session, menu_day_id: UUID) -> list[UUID]:
    return list(
        session.scalars(select(MenuDayItem.dish_id).where(MenuDayItem.menu_day_id == menu_day_id))
    )


def load_served_dish_ids(session: Session, *, on_date: date, meal_type: MealType) -> list[UUID]:
    """那天实际记录了出餐份数的菜。"""
    return list(
        session.scalars(
            select(DailyLogItem.dish_id)
            .join(DailyLog, DailyLog.id == DailyLogItem.daily_log_id)
            .where(DailyLog.date == on_date, DailyLog.meal_type == meal_type)
        )
    )


def load_ingredient_usage(
    session: Session, dish_ids: Sequence[UUID]
) -> dict[UUID, list[tuple[str, str, Decimal, Decimal | None]]]:
    """每道菜的用料：名称、单位、单份用量、单价。

    一次取全而不是逐道菜查：采购建议要把当天所有菜的需求汇总，
    逐道菜的往返会把「生成一次建议」变成几十次数据库往返。
    """
    if not dish_ids:
        return {}
    rows = session.execute(
        select(
            RecipeItem.dish_id,
            Ingredient.name,
            RecipeItem.quantity_per_serving_g,
            Ingredient.unit_price,
        )
        .join(Ingredient, Ingredient.id == RecipeItem.ingredient_id)
        .where(RecipeItem.dish_id.in_(dish_ids))
    ).all()
    usage: dict[UUID, list[tuple[str, str, Decimal, Decimal | None]]] = defaultdict(list)
    for dish_id, name, quantity, price in rows:
        # 食材一律按克计（配方用量本身就是克），单位写死不会错
        usage[dish_id].append((name, "克", Decimal(quantity), price))

    seasoning_rows = session.execute(
        select(
            RecipeSeasoning.dish_id,
            Seasoning.name,
            Seasoning.unit,
            RecipeSeasoning.quantity_per_serving_g,
            Seasoning.unit_price,
        )
        .join(Seasoning, Seasoning.id == RecipeSeasoning.seasoning_id)
        .where(RecipeSeasoning.dish_id.in_(dish_ids))
    ).all()
    for dish_id, name, unit, quantity, price in seasoning_rows:
        usage[dish_id].append((name, unit or "克", Decimal(quantity), price))
    return dict(usage)


def replace_forecasts(
    session: Session,
    *,
    on_date: date,
    meal_type: MealType,
    model_version: str,
    rows: list[dict[str, object]],
) -> None:
    """同一 (日期, 餐次, 模型版本) 重算时整份替换。"""
    session.execute(
        delete(Forecast).where(
            Forecast.date == on_date,
            Forecast.meal_type == meal_type,
            Forecast.model_version == model_version,
        )
    )
    for row in rows:
        session.add(
            Forecast(
                date=on_date,
                meal_type=meal_type,
                model_version=model_version,
                **row,
            )
        )
    session.flush()


def load_forecasts(
    session: Session, *, on_date: date, meal_type: MealType, model_version: str
) -> list[Forecast]:
    return list(
        session.scalars(
            select(Forecast)
            .where(
                Forecast.date == on_date,
                Forecast.meal_type == meal_type,
                Forecast.model_version == model_version,
            )
            .order_by(Forecast.predicted_servings.desc())
        ).all()
    )

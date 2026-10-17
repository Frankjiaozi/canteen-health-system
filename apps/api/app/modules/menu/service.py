"""菜单日的写操作。

只有一件事：把"某天某一餐实际供应了哪些菜"确认下来。它由采集页驱动——
需求里要求"在采集页内直接勾选今日实际供应的菜品，勾选即写入当天菜单日"，
所以这里是跨域调用的入口，采集域通过它写菜单，不直接碰 menu 的表。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError
from app.modules.collection import repository as collection_repository
from app.modules.menu import repository
from app.modules.menu.locking import lock_meal
from app.shared.enums import MealType


@dataclass
class ConfirmedDish:
    """采集时确认的一道菜。"""

    dish_id: UUID
    #: 与计划不一致的临时替换
    is_substituted: bool = False
    note: str | None = None


@dataclass
class PlannedDish:
    """排菜单时计划供应的一道菜。"""

    dish_id: UUID
    #: 计划做多少份。预测不出来时可以是空的——空着比编一个数诚实
    planned_servings: Decimal | None = None


def confirm_menu_day(
    session: Session,
    *,
    on_date: date,
    meal_type: MealType,
    dishes: list[ConfirmedDish],
    created_by: UUID | None = None,
) -> UUID:
    """把当餐实际供应的菜品整份写入菜单日，返回菜单日 ID。"""
    lock_meal(session, on_date, meal_type)
    menu_day = repository.ensure_menu_day(
        session, on_date=on_date, meal_type=meal_type, created_by=created_by
    )
    repository.replace_items(
        session,
        menu_day_id=menu_day.id,
        items=[(row.dish_id, row.is_substituted, row.note, None) for row in dishes],
    )
    return menu_day.id


def plan_menu_day(
    session: Session,
    *,
    on_date: date,
    meal_type: MealType,
    dishes: list[PlannedDish],
    created_by: UUID | None = None,
) -> UUID:
    """把「明天做哪几道菜、各做多少份」写进那一天的菜单日——菜单的**计划**。

    菜单日在采集页里是「实际供应了哪些菜」，在这里是「计划供应哪些菜」，
    同一条记录先后扮演两个角色：采集页打开时先按计划勾好，提交时按实际整份覆盖。
    这样「一天供应了哪些菜」始终只有一份数据，不会出现计划与实际两张表打架。

    计划份数写进 `planned_servings`，提交采集时**保留**（见 repository.replace_items），
    因此事后能对上「计划做 812 份、实际做了 700 份」。
    """
    lock_meal(session, on_date, meal_type)
    if collection_repository.get_log(session, on_date=on_date, meal_type=meal_type):
        raise BusinessRuleError("这餐已经录过采集，不能用计划覆盖实际供应")
    menu_day = repository.ensure_menu_day(
        session, on_date=on_date, meal_type=meal_type, created_by=created_by
    )
    repository.replace_items(
        session,
        menu_day_id=menu_day.id,
        items=[
            # note 留给「临时替换」用，计划这件事不写进去——计划与实际的分野
            # 是靠「有没有计划份数、有没有当天的采集记录」判断的，往备注里塞标记迟早会串味
            (row.dish_id, False, None, row.planned_servings)
            for row in dishes
        ],
    )
    return menu_day.id

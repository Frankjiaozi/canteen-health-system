"""菜单日的写操作。

只有一件事：把"某天某一餐实际供应了哪些菜"确认下来。它由采集页驱动——
需求里要求"在采集页内直接勾选今日实际供应的菜品，勾选即写入当天菜单日"，
所以这里是跨域调用的入口，采集域通过它写菜单，不直接碰 menu 的表。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.menu import repository
from app.shared.enums import MealType


@dataclass
class ConfirmedDish:
    """采集时确认的一道菜。"""

    dish_id: UUID
    #: 与计划不一致的临时替换
    is_substituted: bool = False
    note: str | None = None


def confirm_menu_day(
    session: Session,
    *,
    on_date: date,
    meal_type: MealType,
    dishes: list[ConfirmedDish],
    created_by: UUID | None = None,
) -> UUID:
    """把当餐实际供应的菜品整份写入菜单日，返回菜单日 ID。"""
    menu_day = repository.ensure_menu_day(
        session, on_date=on_date, meal_type=meal_type, created_by=created_by
    )
    repository.replace_items(
        session,
        menu_day_id=menu_day.id,
        items=[(row.dish_id, row.is_substituted, row.note) for row in dishes],
    )
    return menu_day.id

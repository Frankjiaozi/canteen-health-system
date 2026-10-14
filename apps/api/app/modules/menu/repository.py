"""菜单日的数据访问。

本域的读写都很薄：菜单的"聪明"部分（轮换编排、推荐生成）在 recommendation 域，
这里只负责把某天某一餐实际供应了哪些菜如实落库。
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.modules.menu.models import MenuDay, MenuDayItem
from app.shared.enums import MealType


def get_menu_day(session: Session, *, on_date: date, meal_type: MealType) -> MenuDay | None:
    return session.scalar(
        select(MenuDay).where(MenuDay.date == on_date, MenuDay.meal_type == meal_type)
    )


def load_items(session: Session, menu_day_id: UUID) -> list[MenuDayItem]:
    return list(
        session.scalars(
            select(MenuDayItem)
            .where(MenuDayItem.menu_day_id == menu_day_id)
            .order_by(MenuDayItem.created_at)
        ).all()
    )


def ensure_menu_day(
    session: Session, *, on_date: date, meal_type: MealType, created_by: UUID | None
) -> MenuDay:
    menu_day = get_menu_day(session, on_date=on_date, meal_type=meal_type)
    if menu_day is None:
        menu_day = MenuDay(date=on_date, meal_type=meal_type, created_by=created_by)
        session.add(menu_day)
        session.flush()
    return menu_day


def replace_items(
    session: Session,
    *,
    menu_day_id: UUID,
    items: list[tuple[UUID, bool, str | None]],
) -> None:
    """整体替换菜单明细。

    采集页提交的是"今天实际供应的全部菜品"这一份完整清单，因此按整体替换处理——
    逐条 diff 只会让"某道菜被取消了"这件事变得难以表达。被替换掉的明细里，
    历史营养结果不受影响（它们挂在菜品与日期上，不挂在这张表上）。
    """
    session.execute(delete(MenuDayItem).where(MenuDayItem.menu_day_id == menu_day_id))
    for dish_id, is_substituted, note in items:
        session.add(
            MenuDayItem(
                menu_day_id=menu_day_id,
                dish_id=dish_id,
                is_substituted=is_substituted,
                substitution_note=note,
            )
        )
    session.flush()

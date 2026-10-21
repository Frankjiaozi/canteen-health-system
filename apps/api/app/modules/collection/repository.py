"""每日采集的数据访问。"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.collection.models import DailyLog, DailyLogItem
from app.modules.dish.models import Dish
from app.modules.menu.models import MenuDay, MenuDayItem
from app.shared.enums import MealType


def get_log(session: Session, *, on_date: date, meal_type: MealType) -> DailyLog | None:
    return session.scalar(
        select(DailyLog)
        .where(DailyLog.date == on_date, DailyLog.meal_type == meal_type)
        .execution_options(populate_existing=True)
    )


def load_items(session: Session, daily_log_id: UUID) -> list[DailyLogItem]:
    return list(
        session.scalars(
            select(DailyLogItem)
            .where(DailyLogItem.daily_log_id == daily_log_id)
            .order_by(DailyLogItem.created_at)
            .execution_options(populate_existing=True)
        ).all()
    )


def load_menu_items(session: Session, *, on_date: date, meal_type: MealType) -> list[MenuDayItem]:
    """当天菜单上的明细行（菜单还没排时是空列表）。

    返回明细行而不是菜品：采集单既要知道有哪些菜，也要知道它的**计划份数**，
    后者只在明细行上。
    """
    return list(
        session.scalars(
            select(MenuDayItem)
            .join(MenuDay, MenuDay.id == MenuDayItem.menu_day_id)
            .where(MenuDay.date == on_date, MenuDay.meal_type == meal_type)
        ).all()
    )


def load_active_dishes(session: Session, *, include_ids: set[UUID] | None = None) -> list[Dish]:
    """全部在用的菜品，按类别与名称排序。

    当天还没有菜单时，采集页要靠它把可选菜品列出来——否则「勾选今日实际供应的菜品」
    这件事第一次根本无从下手。
    """
    return list(
        session.scalars(
            select(Dish)
            .where(or_(Dish.is_active.is_(True), Dish.id.in_(include_ids or set())))
            .order_by(Dish.category, Dish.name)
        ).all()
    )


def upsert_log(
    session: Session,
    *,
    on_date: date,
    meal_type: MealType,
    diner_count: int,
    oil_total_g: Decimal | None,
    salt_total_g: Decimal | None,
    sugar_total_g: Decimal | None,
    leftover_weight_g: Decimal | None,
    note: str | None,
    anomaly_flags: list[str],
    submitted_by: UUID | None,
    submitted_at: datetime,
) -> DailyLog:
    log = get_log(session, on_date=on_date, meal_type=meal_type)
    if log is None:
        log = DailyLog(date=on_date, meal_type=meal_type)
        session.add(log)
    log.diner_count = diner_count
    log.oil_total_g = oil_total_g
    log.salt_total_g = salt_total_g
    log.sugar_total_g = sugar_total_g
    log.leftover_weight_g = leftover_weight_g
    log.note = note
    log.anomaly_flags = anomaly_flags
    log.submitted_by = submitted_by
    log.submitted_at = submitted_at
    session.flush()
    return log


def replace_items(
    session: Session,
    *,
    daily_log_id: UUID,
    items: list[dict[str, object]],
) -> None:
    """整体替换明细：采集单提交的是"今天这道菜出了多少份、剩了多少"的完整清单。"""
    session.execute(delete(DailyLogItem).where(DailyLogItem.daily_log_id == daily_log_id))
    for row in items:
        session.add(DailyLogItem(daily_log_id=daily_log_id, **row))
    session.flush()


def delete_log(session: Session, *, log: DailyLog) -> None:
    """整份删掉一条采集记录（含明细）。

    只给「撤回一次误录」用：采集记录本身是原始数据，正常业务里不该有删除入口。
    菜单日不在这里处理——它可能来自计划，删完要不要恢复由调用方决定。
    """
    session.execute(delete(DailyLogItem).where(DailyLogItem.daily_log_id == log.id))
    session.delete(log)
    session.flush()


def list_logs(
    session: Session, *, page: int, page_size: int, start: date | None, end: date | None
) -> tuple[list[tuple[DailyLog, int, Decimal | None, str | None]], int]:
    """分页列出采集记录，附带菜品数、出餐总重与提交人。

    出餐总重按「出餐份数 × 该菜标准份量」推算，与看板的浪费率口径一致——
    两处各算一遍迟早会对不上。
    """
    conditions = []
    if start is not None:
        conditions.append(DailyLog.date >= start)
    if end is not None:
        conditions.append(DailyLog.date <= end)

    dish_count = (
        select(
            DailyLogItem.daily_log_id.label("log_id"),
            func.count(DailyLogItem.id).label("dish_count"),
            func.sum(DailyLogItem.servings_produced * Dish.standard_serving_g).label("produced_g"),
        )
        .join(Dish, Dish.id == DailyLogItem.dish_id)
        .group_by(DailyLogItem.daily_log_id)
        .subquery()
    )

    total = session.scalar(select(func.count()).select_from(DailyLog).where(*conditions)) or 0
    rows = session.execute(
        select(
            DailyLog,
            func.coalesce(dish_count.c.dish_count, 0),
            dish_count.c.produced_g,
            User.display_name,
        )
        .outerjoin(dish_count, dish_count.c.log_id == DailyLog.id)
        .outerjoin(User, User.id == DailyLog.submitted_by)
        .where(*conditions)
        .order_by(DailyLog.date.desc(), DailyLog.meal_type)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return [(row[0], int(row[1]), row[2], row[3]) for row in rows], int(total)


def set_anomaly_flag(session: Session, *, log: DailyLog, flag: str, enabled: bool) -> bool:
    """增删一个标记，其余标记原样保留。返回是否真的改动了。

    只动自己那一个：录入员勾的"临时接待"和系统判的"用量对不上"是两件事，
    重算校准时绝不能把人工标记一并抹掉。
    """
    current = list(log.anomaly_flags or [])
    if enabled and flag not in current:
        log.anomaly_flags = [*current, flag]
        return True
    if not enabled and flag in current:
        log.anomaly_flags = [item for item in current if item != flag]
        return True
    return False

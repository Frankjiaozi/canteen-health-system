"""调味料库数据访问。"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.modules.seasoning.models import Seasoning
from app.shared.enums import SeasoningCategory


def _apply_filters(
    statement: Select[Seasoning],
    *,
    keyword: str | None,
    category: SeasoningCategory | None,
    include_inactive: bool,
) -> Select[Seasoning]:
    if not include_inactive:
        statement = statement.where(Seasoning.is_active.is_(True))
    if category is not None:
        statement = statement.where(Seasoning.category == category)
    if keyword:
        pattern = f"%{keyword.strip()}%"
        statement = statement.where(
            or_(
                Seasoning.name.ilike(pattern),
                func.coalesce(Seasoning.data_source, "").ilike(pattern),
            )
        )
    return statement


def list_page(
    session: Session,
    *,
    keyword: str | None,
    category: SeasoningCategory | None,
    include_inactive: bool,
    page: int,
    page_size: int,
) -> tuple[list[Seasoning], int]:
    base = _apply_filters(
        select(Seasoning),
        keyword=keyword,
        category=category,
        include_inactive=include_inactive,
    )

    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    statement = (
        base.order_by(Seasoning.category, Seasoning.name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows: list[Seasoning] = list(session.scalars(statement).all())
    return rows, total


def get(session: Session, seasoning_id: UUID) -> Seasoning | None:
    return session.get(Seasoning, seasoning_id)


def find_by_name(session: Session, name: str) -> Seasoning | None:
    return session.scalar(select(Seasoning).where(Seasoning.name == name))


def names_in_use(session: Session, names: Sequence[str]) -> set[str]:
    """返回给定名称中已存在的那些，供批量导入一次性判断。"""
    if not names:
        return set()
    return set(session.scalars(select(Seasoning.name).where(Seasoning.name.in_(names))).all())


def ids_by_name(session: Session, names: Sequence[str]) -> dict[str, UUID]:
    if not names:
        return {}
    rows = session.execute(
        select(Seasoning.name, Seasoning.id).where(Seasoning.name.in_(names))
    ).all()
    return {row[0]: row[1] for row in rows}

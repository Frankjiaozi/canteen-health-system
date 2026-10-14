"""食材库数据访问。"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.modules.ingredient.models import Ingredient
from app.shared.enums import IngredientCategory


def _apply_filters(
    statement: Select[Ingredient],
    *,
    keyword: str | None,
    category: IngredientCategory | None,
    include_inactive: bool,
) -> Select[Ingredient]:
    if not include_inactive:
        statement = statement.where(Ingredient.is_active.is_(True))
    if category is not None:
        statement = statement.where(Ingredient.category == category)
    if keyword:
        pattern = f"%{keyword.strip()}%"
        statement = statement.where(
            or_(
                Ingredient.name.ilike(pattern),
                Ingredient.data_source.ilike(pattern),
            )
        )
    return statement


def list_page(
    session: Session,
    *,
    keyword: str | None,
    category: IngredientCategory | None,
    include_inactive: bool,
    page: int,
    page_size: int,
) -> tuple[list[Ingredient], int]:
    base = _apply_filters(
        select(Ingredient), keyword=keyword, category=category, include_inactive=include_inactive
    )

    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    statement = (
        base.order_by(Ingredient.category, Ingredient.name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows: list[Ingredient] = list(session.scalars(statement).all())
    return rows, total


def get(session: Session, ingredient_id: UUID) -> Ingredient | None:
    return session.get(Ingredient, ingredient_id)


def find_by_name(session: Session, name: str) -> Ingredient | None:
    return session.scalar(select(Ingredient).where(Ingredient.name == name))


def names_in_use(session: Session, names: Sequence[str]) -> set[str]:
    """返回给定名称中已存在的那些，供批量导入一次性判断新增还是更新。"""
    if not names:
        return set()
    return set(session.scalars(select(Ingredient.name).where(Ingredient.name.in_(names))).all())


def ids_by_name(session: Session, names: Sequence[str]) -> dict[str, UUID]:
    """名称 → 主键。批量导入时一次性把引用关系查出来，避免逐行查询。"""
    if not names:
        return {}
    rows = session.execute(
        select(Ingredient.name, Ingredient.id).where(Ingredient.name.in_(names))
    ).all()
    return {row[0]: row[1] for row in rows}

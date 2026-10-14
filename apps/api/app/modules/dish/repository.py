"""菜品与配方数据访问。"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import TypedDict
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.modules.dish.models import Dish, RecipeItem, RecipeSeasoning
from app.modules.ingredient.models import Ingredient
from app.modules.menu.models import MenuDayItem
from app.modules.nutrition.models import DishNutrition
from app.modules.seasoning.models import Seasoning
from app.shared.enums import DishCategory, NutrientCaliber, NutritionValueType


class IngredientLineValues(TypedDict):
    """配方里一行食材的可写字段。用 TypedDict 而不是 dict[str, object]，
    是为了让「把行写进模型」这一步仍然受类型检查。"""

    ingredient_id: UUID
    quantity_per_serving_g: Decimal
    edible_ratio_override: Decimal | None
    note: str | None


class SeasoningLineValues(TypedDict):
    seasoning_id: UUID
    quantity_per_serving_g: Decimal
    note: str | None


def _apply_filters(
    statement: Select[Dish],
    *,
    keyword: str | None,
    category: DishCategory | None,
    include_inactive: bool,
) -> Select[Dish]:
    if not include_inactive:
        statement = statement.where(Dish.is_active.is_(True))
    if category is not None:
        statement = statement.where(Dish.category == category)
    if keyword:
        statement = statement.where(Dish.name.ilike(f"%{keyword.strip()}%"))
    return statement


def list_page(
    session: Session,
    *,
    keyword: str | None,
    category: DishCategory | None,
    include_inactive: bool,
    page: int,
    page_size: int,
) -> tuple[list[Dish], int]:
    base = _apply_filters(
        select(Dish), keyword=keyword, category=category, include_inactive=include_inactive
    )

    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    statement = (
        base.order_by(Dish.category, Dish.name).offset((page - 1) * page_size).limit(page_size)
    )
    rows: list[Dish] = list(session.scalars(statement).all())
    return rows, total


def get(session: Session, dish_id: UUID) -> Dish | None:
    return session.get(Dish, dish_id)


def get_many(session: Session, dish_ids: Sequence[UUID]) -> dict[UUID, Dish]:
    if not dish_ids:
        return {}
    rows = session.scalars(select(Dish).where(Dish.id.in_(dish_ids))).all()
    return {row.id: row for row in rows}


def find_by_name(session: Session, name: str) -> Dish | None:
    return session.scalar(select(Dish).where(Dish.name == name))


def names_in_use(session: Session, names: Sequence[str]) -> set[str]:
    """返回给定名称中已存在的那些，供批量导入一次性判断。"""
    if not names:
        return set()
    return set(session.scalars(select(Dish.name).where(Dish.name.in_(names))).all())


def load_recipe_rows(
    session: Session, dish_ids: Sequence[UUID]
) -> tuple[list[tuple[RecipeItem, Ingredient]], list[tuple[RecipeSeasoning, Seasoning]]]:
    """一次性把配方明细连同食材、调味料取回来，避免逐道菜查询。"""
    if not dish_ids:
        return [], []

    ingredient_rows = session.execute(
        select(RecipeItem, Ingredient)
        .join(Ingredient, Ingredient.id == RecipeItem.ingredient_id)
        .where(RecipeItem.dish_id.in_(dish_ids))
    ).all()
    seasoning_rows = session.execute(
        select(RecipeSeasoning, Seasoning)
        .join(Seasoning, Seasoning.id == RecipeSeasoning.seasoning_id)
        .where(RecipeSeasoning.dish_id.in_(dish_ids))
    ).all()
    return list(ingredient_rows), list(seasoning_rows)


def latest_per_serving_nutrition(
    session: Session, dish_ids: Sequence[UUID]
) -> dict[UUID, DishNutrition]:
    """每道菜最近一次的单份理论营养，用于列表里的摘要。

    做法是先按菜品取到各自的「最新日期」，再回联出对应那一行。一次查询取回全部摘要，
    也不依赖 PostgreSQL 特有的 DISTINCT ON 写法。
    """
    if not dish_ids:
        return {}

    scope = (
        DishNutrition.dish_id.in_(dish_ids),
        DishNutrition.caliber == NutrientCaliber.PER_SERVING,
        DishNutrition.value_type == NutritionValueType.THEORETICAL,
    )
    latest_dates = (
        select(DishNutrition.dish_id, func.max(DishNutrition.date).label("latest_date"))
        .where(*scope)
        .group_by(DishNutrition.dish_id)
        .subquery()
    )
    rows = session.scalars(
        select(DishNutrition)
        .join(
            latest_dates,
            (DishNutrition.dish_id == latest_dates.c.dish_id)
            & (DishNutrition.date == latest_dates.c.latest_date),
        )
        .where(*scope)
    ).all()
    return {row.dish_id: row for row in rows}


def replace_recipe(
    session: Session,
    dish_id: UUID,
    *,
    ingredients: list[IngredientLineValues],
    seasonings: list[SeasoningLineValues],
) -> None:
    """按自然键同步配方：对得上的行原地更新，多余的删除，新出现的插入。

    语义上仍是「整体替换」，但**不换行主键**。先删后插看起来更简单，代价是每次
    编辑都换一批新 id——种子脚本按确定性 id 写入，两边就会在 (dish_id, ingredient_id)
    这个唯一约束上撞车；留痕里引用的行标识也会跟着失效。
    """
    _sync_ingredient_lines(session, dish_id, ingredients)
    _sync_seasoning_lines(session, dish_id, seasonings)
    session.flush()


def _sync_ingredient_lines(
    session: Session, dish_id: UUID, rows: list[IngredientLineValues]
) -> None:
    existing = {
        row.ingredient_id: row
        for row in session.scalars(select(RecipeItem).where(RecipeItem.dish_id == dish_id)).all()
    }
    incoming: set[UUID] = set()
    for row in rows:
        key = row["ingredient_id"]
        incoming.add(key)
        current = existing.get(key)
        if current is None:
            session.add(RecipeItem(dish_id=dish_id, **row))
            continue
        current.quantity_per_serving_g = row["quantity_per_serving_g"]
        current.edible_ratio_override = row["edible_ratio_override"]
        current.note = row["note"]

    for key, current in existing.items():
        if key not in incoming:
            session.delete(current)


def _sync_seasoning_lines(session: Session, dish_id: UUID, rows: list[SeasoningLineValues]) -> None:
    existing = {
        row.seasoning_id: row
        for row in session.scalars(
            select(RecipeSeasoning).where(RecipeSeasoning.dish_id == dish_id)
        ).all()
    }
    incoming: set[UUID] = set()
    for row in rows:
        key = row["seasoning_id"]
        incoming.add(key)
        current = existing.get(key)
        if current is None:
            session.add(RecipeSeasoning(dish_id=dish_id, **row))
            continue
        current.quantity_per_serving_g = row["quantity_per_serving_g"]
        current.note = row["note"]

    for key, current in existing.items():
        if key not in incoming:
            session.delete(current)


def active_ids(session: Session, *, ingredient_ids: Sequence[UUID]) -> set[UUID]:
    if not ingredient_ids:
        return set()
    return set(
        session.scalars(select(Ingredient.id).where(Ingredient.id.in_(ingredient_ids))).all()
    )


def active_seasoning_ids(session: Session, *, seasoning_ids: Sequence[UUID]) -> set[UUID]:
    if not seasoning_ids:
        return set()
    return set(session.scalars(select(Seasoning.id).where(Seasoning.id.in_(seasoning_ids))).all())


def dish_usage_count(session: Session, dish_id: UUID) -> int:
    """被菜单引用过多少次，用于停用前的提示。"""
    return (
        session.scalar(
            select(func.count()).select_from(MenuDayItem).where(MenuDayItem.dish_id == dish_id)
        )
        or 0
    )

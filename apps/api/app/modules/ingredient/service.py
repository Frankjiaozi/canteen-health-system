"""食材库业务规则。"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.modules.audit import service as audit_service
from app.modules.ingredient import repository
from app.modules.ingredient.models import Ingredient
from app.modules.ingredient.schemas import (
    IngredientCreate,
    IngredientPage,
    IngredientRead,
    IngredientUpdate,
)
from app.shared.enums import AuditAction, IngredientCategory

ENTITY_TYPE = "ingredient"

#: 各字段落库时的小数位，与数据模型里的 Numeric 精度一致。
#: 返回前统一按这个精度取整，否则新建（回显请求值 25.5）与查询
#: （数据库读回 25.50）会给出两种写法，前端拿到同一个值却对不上字符串。
FIELD_SCALES: dict[str, int] = {
    "energy_kcal": 2,
    "protein_g": 3,
    "fat_g": 3,
    "carb_g": 3,
    "sodium_mg": 2,
    "edible_ratio": 4,
    "unit_price": 2,
}


def to_read(ingredient: Ingredient) -> IngredientRead:
    return IngredientRead(
        id=ingredient.id,
        name=ingredient.name,
        category=ingredient.category,
        category_label=ingredient.category.label,
        energy_kcal=_scaled(ingredient.energy_kcal, "energy_kcal"),
        protein_g=_scaled(ingredient.protein_g, "protein_g"),
        fat_g=_scaled(ingredient.fat_g, "fat_g"),
        carb_g=_scaled(ingredient.carb_g, "carb_g"),
        sodium_mg=_scaled(ingredient.sodium_mg, "sodium_mg"),
        edible_ratio=_scaled(ingredient.edible_ratio, "edible_ratio") or Decimal("1.0000"),
        unit_price=_scaled(ingredient.unit_price, "unit_price"),
        data_source=ingredient.data_source,
        source_version=ingredient.source_version,
        note=ingredient.note,
        is_active=ingredient.is_active,
        created_at=ingredient.created_at,
        updated_at=ingredient.updated_at,
    )


def list_ingredients(
    session: Session,
    *,
    keyword: str | None = None,
    category: IngredientCategory | None = None,
    include_inactive: bool = False,
    page: int = 1,
    page_size: int = 20,
) -> IngredientPage:
    rows, total = repository.list_page(
        session,
        keyword=keyword,
        category=category,
        include_inactive=include_inactive,
        page=page,
        page_size=page_size,
    )
    return IngredientPage(
        items=[to_read(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


def get_ingredient(session: Session, ingredient_id: UUID) -> Ingredient:
    ingredient = repository.get(session, ingredient_id)
    if ingredient is None:
        raise NotFoundError("食材不存在")
    return ingredient


def create_ingredient(
    session: Session,
    payload: IngredientCreate,
    *,
    actor_id: UUID | None = None,
    actor_name: str | None = None,
    audit_note: str | None = None,
) -> Ingredient:
    """新增食材。`audit_note` 用来标出这条数据是怎么来的。

    AI 助手代录时传「经 AI 助手提议、由本人确认后创建」——留痕里要能分清
    「人自己在页面上录的」与「助手提议、人确认的」，否则审计时看不出差别。
    """
    if repository.find_by_name(session, payload.name) is not None:
        raise ConflictError(f"食材「{payload.name}」已存在")

    ingredient = Ingredient(**payload.model_dump())
    session.add(ingredient)
    session.flush()

    audit_service.record(
        session,
        entity_type=ENTITY_TYPE,
        entity_id=ingredient.id,
        action=AuditAction.CREATE,
        actor_id=actor_id,
        actor_name=actor_name,
        after=_snapshot(ingredient),
        note=audit_note,
    )
    session.commit()
    return ingredient


def update_ingredient(
    session: Session,
    ingredient_id: UUID,
    payload: IngredientUpdate,
    *,
    actor_id: UUID | None = None,
    actor_name: str | None = None,
) -> Ingredient:
    ingredient = get_ingredient(session, ingredient_id)
    changes = payload.model_dump(exclude_unset=True)

    new_name = changes.get("name")
    if new_name and new_name != ingredient.name:
        existing = repository.find_by_name(session, new_name)
        if existing is not None and existing.id != ingredient.id:
            raise ConflictError(f"食材「{new_name}」已存在")

    before = _snapshot(ingredient)
    for field, value in changes.items():
        setattr(ingredient, field, value)
    session.flush()
    after = _snapshot(ingredient)

    if before != after:
        audit_service.record(
            session,
            entity_type=ENTITY_TYPE,
            entity_id=ingredient.id,
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            actor_name=actor_name,
            before=before,
            after=after,
        )
    session.commit()
    return ingredient


def deactivate_ingredient(
    session: Session,
    ingredient_id: UUID,
    *,
    actor_id: UUID | None = None,
    actor_name: str | None = None,
    note: str | None = None,
) -> Ingredient:
    """停用（软删除）食材。

    不做物理删除：被配方、菜单或每日记录引用过的数据一旦消失，
    历史营养结果就再也回溯不了。
    """
    ingredient = get_ingredient(session, ingredient_id)
    if not ingredient.is_active:
        return ingredient

    ingredient.is_active = False
    session.flush()

    audit_service.record(
        session,
        entity_type=ENTITY_TYPE,
        entity_id=ingredient.id,
        action=AuditAction.DELETE,
        actor_id=actor_id,
        actor_name=actor_name,
        before=_snapshot(ingredient),
        note=note or "停用食材（软删除）",
    )
    session.commit()
    return ingredient


def _snapshot(ingredient: Ingredient) -> dict[str, Any]:
    """留痕用的字段快照。把 Decimal 与枚举转成可 JSON 化的形式。"""
    return {
        "name": ingredient.name,
        "category": ingredient.category.value,
        "energy_kcal": _as_str(ingredient.energy_kcal),
        "protein_g": _as_str(ingredient.protein_g),
        "fat_g": _as_str(ingredient.fat_g),
        "carb_g": _as_str(ingredient.carb_g),
        "sodium_mg": _as_str(ingredient.sodium_mg),
        "edible_ratio": _as_str(ingredient.edible_ratio),
        "unit_price": _as_str(ingredient.unit_price),
        "data_source": ingredient.data_source,
        "source_version": ingredient.source_version,
        "note": ingredient.note,
        "is_active": ingredient.is_active,
    }


def _as_str(value: Any) -> str | None:
    return None if value is None else str(value)


def upsert_many(session: Session, rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    """批量导入专用：按名称新增或更新。只 flush 不 commit，由调用方统一提交。"""
    counts = {"created": 0, "updated": 0}
    for row in rows:
        name = str(row["name"])
        existing = repository.find_by_name(session, name)
        if existing is None:
            session.add(Ingredient(**row))
            counts["created"] += 1
            continue

        changed = [field for field, value in row.items() if getattr(existing, field) != value]
        for field in changed:
            setattr(existing, field, row[field])
        if changed:
            counts["updated"] += 1
    session.flush()
    return counts


def _scaled(value: Decimal | None, field: str) -> Decimal | None:
    if value is None:
        return None
    return value.quantize(Decimal(1).scaleb(-FIELD_SCALES[field]), rounding=ROUND_HALF_UP)

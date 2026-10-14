"""调味料库业务规则。"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.modules.audit import service as audit_service
from app.modules.seasoning import repository
from app.modules.seasoning.models import Seasoning
from app.modules.seasoning.schemas import (
    SeasoningCreate,
    SeasoningPage,
    SeasoningRead,
    SeasoningUpdate,
)
from app.shared.decimals import scale_field, snapshot
from app.shared.enums import AuditAction, SeasoningCategory

ENTITY_TYPE = "seasoning"


def to_read(seasoning: Seasoning) -> SeasoningRead:
    return SeasoningRead(
        id=seasoning.id,
        name=seasoning.name,
        category=seasoning.category,
        category_label=seasoning.category.label,
        unit=seasoning.unit,
        energy_kcal=scale_field(seasoning.energy_kcal, "energy_kcal"),
        protein_g=scale_field(seasoning.protein_g, "protein_g"),
        fat_g=scale_field(seasoning.fat_g, "fat_g"),
        carb_g=scale_field(seasoning.carb_g, "carb_g"),
        sodium_mg=scale_field(seasoning.sodium_mg, "sodium_mg"),
        unit_price=scale_field(seasoning.unit_price, "unit_price"),
        data_source=seasoning.data_source,
        note=seasoning.note,
        is_active=seasoning.is_active,
        created_at=seasoning.created_at,
        updated_at=seasoning.updated_at,
    )


def list_seasonings(
    session: Session,
    *,
    keyword: str | None = None,
    category: SeasoningCategory | None = None,
    include_inactive: bool = False,
    page: int = 1,
    page_size: int = 20,
) -> SeasoningPage:
    rows, total = repository.list_page(
        session,
        keyword=keyword,
        category=category,
        include_inactive=include_inactive,
        page=page,
        page_size=page_size,
    )
    return SeasoningPage(
        items=[to_read(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


def get_seasoning(session: Session, seasoning_id: UUID) -> Seasoning:
    seasoning = repository.get(session, seasoning_id)
    if seasoning is None:
        raise NotFoundError("调味料不存在")
    return seasoning


def create_seasoning(
    session: Session,
    payload: SeasoningCreate,
    *,
    actor_id: UUID | None = None,
    actor_name: str | None = None,
) -> Seasoning:
    if repository.find_by_name(session, payload.name) is not None:
        raise ConflictError(f"调味料「{payload.name}」已存在")

    seasoning = Seasoning(**payload.model_dump())
    session.add(seasoning)
    session.flush()

    audit_service.record(
        session,
        entity_type=ENTITY_TYPE,
        entity_id=seasoning.id,
        action=AuditAction.CREATE,
        actor_id=actor_id,
        actor_name=actor_name,
        after=_snapshot(seasoning),
    )
    session.commit()
    return seasoning


def update_seasoning(
    session: Session,
    seasoning_id: UUID,
    payload: SeasoningUpdate,
    *,
    actor_id: UUID | None = None,
    actor_name: str | None = None,
) -> Seasoning:
    seasoning = get_seasoning(session, seasoning_id)
    changes = payload.model_dump(exclude_unset=True)

    new_name = changes.get("name")
    if new_name and new_name != seasoning.name:
        existing = repository.find_by_name(session, new_name)
        if existing is not None and existing.id != seasoning.id:
            raise ConflictError(f"调味料「{new_name}」已存在")

    before = _snapshot(seasoning)
    for field, value in changes.items():
        setattr(seasoning, field, value)
    session.flush()
    after = _snapshot(seasoning)

    if before != after:
        audit_service.record(
            session,
            entity_type=ENTITY_TYPE,
            entity_id=seasoning.id,
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            actor_name=actor_name,
            before=before,
            after=after,
        )
    session.commit()
    return seasoning


def deactivate_seasoning(
    session: Session,
    seasoning_id: UUID,
    *,
    actor_id: UUID | None = None,
    actor_name: str | None = None,
) -> Seasoning:
    """停用（软删除）。被配方引用过的调味料不能物理删除，否则历史营养结果回溯不了。"""
    seasoning = get_seasoning(session, seasoning_id)
    if not seasoning.is_active:
        return seasoning

    seasoning.is_active = False
    session.flush()

    audit_service.record(
        session,
        entity_type=ENTITY_TYPE,
        entity_id=seasoning.id,
        action=AuditAction.DELETE,
        actor_id=actor_id,
        actor_name=actor_name,
        before=_snapshot(seasoning),
        note="停用调味料（软删除）",
    )
    session.commit()
    return seasoning


def upsert_many(session: Session, rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    """批量导入专用：按名称新增或更新，每行单独留痕。

    刻意不复用单条创建：导入是「一次性把整张表灌进来」，逐条提交既慢，
    又会在中途失败时留下半张表。这里由调用方统一提交。
    """
    counts = {"created": 0, "updated": 0}
    for row in rows:
        name = str(row["name"])
        existing = repository.find_by_name(session, name)
        if existing is None:
            session.add(Seasoning(**row))
            counts["created"] += 1
            continue

        changed = [field for field, value in row.items() if getattr(existing, field) != value]
        for field in changed:
            setattr(existing, field, row[field])
        if changed:
            counts["updated"] += 1
    session.flush()
    return counts


def _snapshot(seasoning: Seasoning) -> dict[str, Any]:
    return {
        "name": seasoning.name,
        "category": seasoning.category.value,
        "unit": seasoning.unit,
        "energy_kcal": snapshot(seasoning.energy_kcal),
        "protein_g": snapshot(seasoning.protein_g),
        "fat_g": snapshot(seasoning.fat_g),
        "carb_g": snapshot(seasoning.carb_g),
        "sodium_mg": snapshot(seasoning.sodium_mg),
        "unit_price": snapshot(seasoning.unit_price),
        "data_source": seasoning.data_source,
        "note": seasoning.note,
        "is_active": seasoning.is_active,
    }

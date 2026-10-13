"""食材库接口。

权限约定：三角色都可以查看食材库（公开大屏的营养数据就来自这里），
但只有食堂录入员与食堂管理员可以增删改——学校管理方是只读的观察者。
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.modules.auth.dependencies import require_roles
from app.modules.auth.schemas import AuthUser
from app.modules.ingredient import service
from app.modules.ingredient.schemas import (
    IngredientCreate,
    IngredientPage,
    IngredientRead,
    IngredientUpdate,
)
from app.shared.enums import IngredientCategory, UserRole

router = APIRouter(prefix="/ingredients", tags=["食材库"])

READ_ROLES = (UserRole.RECORDER, UserRole.CANTEEN_ADMIN, UserRole.SCHOOL_ADMIN)
WRITE_ROLES = (UserRole.RECORDER, UserRole.CANTEEN_ADMIN)


@router.get("", response_model=IngredientPage, summary="分页查询食材")
def list_ingredients(
    keyword: str | None = Query(
        default=None, max_length=64, description="按名称或数据来源模糊匹配"
    ),
    category: IngredientCategory | None = Query(default=None, description="按食材类别过滤"),
    include_inactive: bool = Query(default=False, description="是否包含已停用的食材"),
    page: int = Query(default=1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数"),
    session: Session = Depends(get_session),
    _: AuthUser = Depends(require_roles(*READ_ROLES)),
) -> IngredientPage:
    return service.list_ingredients(
        session,
        keyword=keyword,
        category=category,
        include_inactive=include_inactive,
        page=page,
        page_size=page_size,
    )


@router.get("/{ingredient_id}", response_model=IngredientRead, summary="查询单个食材")
def get_ingredient(
    ingredient_id: UUID,
    session: Session = Depends(get_session),
    _: AuthUser = Depends(require_roles(*READ_ROLES)),
) -> IngredientRead:
    return service.to_read(service.get_ingredient(session, ingredient_id))


@router.post(
    "",
    response_model=IngredientRead,
    status_code=status.HTTP_201_CREATED,
    summary="新增食材",
)
def create_ingredient(
    payload: IngredientCreate,
    session: Session = Depends(get_session),
    actor: AuthUser = Depends(require_roles(*WRITE_ROLES)),
) -> IngredientRead:
    ingredient = service.create_ingredient(
        session, payload, actor_id=actor.id, actor_name=actor.display_name
    )
    return service.to_read(ingredient)


@router.patch("/{ingredient_id}", response_model=IngredientRead, summary="修改食材")
def update_ingredient(
    ingredient_id: UUID,
    payload: IngredientUpdate,
    session: Session = Depends(get_session),
    actor: AuthUser = Depends(require_roles(*WRITE_ROLES)),
) -> IngredientRead:
    ingredient = service.update_ingredient(
        session, ingredient_id, payload, actor_id=actor.id, actor_name=actor.display_name
    )
    return service.to_read(ingredient)


@router.delete(
    "/{ingredient_id}",
    response_model=IngredientRead,
    summary="停用食材（软删除）",
)
def deactivate_ingredient(
    ingredient_id: UUID,
    session: Session = Depends(get_session),
    actor: AuthUser = Depends(require_roles(*WRITE_ROLES)),
) -> IngredientRead:
    ingredient = service.deactivate_ingredient(
        session, ingredient_id, actor_id=actor.id, actor_name=actor.display_name
    )
    return service.to_read(ingredient)

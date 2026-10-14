"""调味料库接口。

与食材库同一套权限约定：三角色都能查看，只有食堂录入员与食堂管理员能增删改。
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.modules.auth.dependencies import require_roles
from app.modules.auth.schemas import AuthUser
from app.modules.seasoning import service
from app.modules.seasoning.schemas import (
    SeasoningCreate,
    SeasoningPage,
    SeasoningRead,
    SeasoningUpdate,
)
from app.shared.enums import SeasoningCategory, UserRole

router = APIRouter(prefix="/seasonings", tags=["调味料库"])

READ_ROLES = (UserRole.RECORDER, UserRole.CANTEEN_ADMIN, UserRole.SCHOOL_ADMIN)
WRITE_ROLES = (UserRole.RECORDER, UserRole.CANTEEN_ADMIN)


@router.get("", response_model=SeasoningPage, summary="分页查询调味料")
def list_seasonings(
    keyword: str | None = Query(
        default=None, max_length=64, description="按名称或数据来源模糊匹配"
    ),
    category: SeasoningCategory | None = Query(default=None, description="按类别过滤"),
    include_inactive: bool = Query(default=False, description="是否包含已停用的调味料"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
    _: AuthUser = Depends(require_roles(*READ_ROLES)),
) -> SeasoningPage:
    return service.list_seasonings(
        session,
        keyword=keyword,
        category=category,
        include_inactive=include_inactive,
        page=page,
        page_size=page_size,
    )


@router.get("/{seasoning_id}", response_model=SeasoningRead, summary="查询单个调味料")
def get_seasoning(
    seasoning_id: UUID,
    session: Session = Depends(get_session),
    _: AuthUser = Depends(require_roles(*READ_ROLES)),
) -> SeasoningRead:
    return service.to_read(service.get_seasoning(session, seasoning_id))


@router.post(
    "", response_model=SeasoningRead, status_code=status.HTTP_201_CREATED, summary="新增调味料"
)
def create_seasoning(
    payload: SeasoningCreate,
    session: Session = Depends(get_session),
    actor: AuthUser = Depends(require_roles(*WRITE_ROLES)),
) -> SeasoningRead:
    seasoning = service.create_seasoning(
        session, payload, actor_id=actor.id, actor_name=actor.display_name
    )
    return service.to_read(seasoning)


@router.patch("/{seasoning_id}", response_model=SeasoningRead, summary="修改调味料")
def update_seasoning(
    seasoning_id: UUID,
    payload: SeasoningUpdate,
    session: Session = Depends(get_session),
    actor: AuthUser = Depends(require_roles(*WRITE_ROLES)),
) -> SeasoningRead:
    seasoning = service.update_seasoning(
        session, seasoning_id, payload, actor_id=actor.id, actor_name=actor.display_name
    )
    return service.to_read(seasoning)


@router.delete("/{seasoning_id}", response_model=SeasoningRead, summary="停用调味料（软删除）")
def deactivate_seasoning(
    seasoning_id: UUID,
    session: Session = Depends(get_session),
    actor: AuthUser = Depends(require_roles(*WRITE_ROLES)),
) -> SeasoningRead:
    seasoning = service.deactivate_seasoning(
        session, seasoning_id, actor_id=actor.id, actor_name=actor.display_name
    )
    return service.to_read(seasoning)

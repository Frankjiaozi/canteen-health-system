"""菜品与配方接口。

配方按「整体替换」维护：`PUT /dishes/{id}/recipe` 一次提交完整配方，
服务端递增配方版本并同步重算这道菜的营养结果。
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.errors import BusinessRuleError, NotFoundError
from app.db.session import get_session
from app.modules.auth.dependencies import require_roles
from app.modules.auth.schemas import AuthUser
from app.modules.dish import images, service
from app.modules.dish.schemas import (
    DishCreate,
    DishDetail,
    DishPage,
    DishUpdate,
    RecipePayload,
    RecipeUpdateResult,
)
from app.shared.enums import DishCategory, UserRole

router = APIRouter(prefix="/dishes", tags=["菜品与配方"])

READ_ROLES = (UserRole.RECORDER, UserRole.CANTEEN_ADMIN, UserRole.SCHOOL_ADMIN)
WRITE_ROLES = (UserRole.RECORDER, UserRole.CANTEEN_ADMIN)


@router.get("", response_model=DishPage, summary="分页查询菜品")
def list_dishes(
    keyword: str | None = Query(default=None, max_length=64, description="按名称模糊匹配"),
    category: DishCategory | None = Query(default=None, description="按菜品类别过滤"),
    include_inactive: bool = Query(default=False, description="是否包含已停用的菜品"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
    _: AuthUser = Depends(require_roles(*READ_ROLES)),
) -> DishPage:
    return service.list_dishes(
        session,
        keyword=keyword,
        category=category,
        include_inactive=include_inactive,
        page=page,
        page_size=page_size,
    )


@router.get("/{dish_id}", response_model=DishDetail, summary="查询单个菜品（含配方）")
def get_dish(
    dish_id: UUID,
    session: Session = Depends(get_session),
    _: AuthUser = Depends(require_roles(*READ_ROLES)),
) -> DishDetail:
    return service.get_dish_detail(session, dish_id)


@router.post("", response_model=DishDetail, status_code=status.HTTP_201_CREATED, summary="新增菜品")
def create_dish(
    payload: DishCreate,
    session: Session = Depends(get_session),
    actor: AuthUser = Depends(require_roles(*WRITE_ROLES)),
) -> DishDetail:
    return service.create_dish(session, payload, actor_id=actor.id, actor_name=actor.display_name)


@router.patch("/{dish_id}", response_model=DishDetail, summary="修改菜品基础信息")
def update_dish(
    dish_id: UUID,
    payload: DishUpdate,
    session: Session = Depends(get_session),
    actor: AuthUser = Depends(require_roles(*WRITE_ROLES)),
) -> DishDetail:
    return service.update_dish(
        session, dish_id, payload, actor_id=actor.id, actor_name=actor.display_name
    )


@router.put(
    "/{dish_id}/recipe",
    response_model=RecipeUpdateResult,
    summary="保存配方（整体替换并重算营养）",
)
def replace_recipe(
    dish_id: UUID,
    payload: RecipePayload,
    session: Session = Depends(get_session),
    actor: AuthUser = Depends(require_roles(*WRITE_ROLES)),
) -> RecipeUpdateResult:
    return service.replace_recipe(
        session, dish_id, payload, actor_id=actor.id, actor_name=actor.display_name
    )


@router.delete("/{dish_id}", response_model=DishDetail, summary="停用菜品（软删除）")
def deactivate_dish(
    dish_id: UUID,
    session: Session = Depends(get_session),
    actor: AuthUser = Depends(require_roles(*WRITE_ROLES)),
) -> DishDetail:
    return service.deactivate_dish(
        session, dish_id, actor_id=actor.id, actor_name=actor.display_name
    )


@router.get("/{dish_id}/image", response_class=FileResponse, summary="读取用户上传的菜品图片")
def get_dish_image(
    dish_id: UUID,
    session: Session = Depends(get_session),
    _: AuthUser = Depends(require_roles(*READ_ROLES)),
) -> FileResponse:
    service.get_dish(session, dish_id)
    path = images.image_path(dish_id)
    if not path.is_file():
        raise NotFoundError("该菜品尚未上传图片")
    return FileResponse(
        path,
        media_type="image/webp",
        headers={"Cache-Control": "private, no-cache", "X-Content-Type-Options": "nosniff"},
    )


@router.put("/{dish_id}/image", response_model=DishDetail, summary="上传或更换菜品图片")
async def upload_dish_image(
    dish_id: UUID,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    _: AuthUser = Depends(require_roles(*WRITE_ROLES)),
) -> DishDetail:
    dish = service.get_dish(session, dish_id)
    if not dish.is_active:
        raise BusinessRuleError("已停用的菜品不能修改图片")
    try:
        content = await file.read(images.MAX_IMAGE_BYTES + 1)
        await run_in_threadpool(images.save_image, dish_id, content, file.content_type)
    finally:
        await file.close()
    return service.get_dish_detail(session, dish_id)


@router.delete("/{dish_id}/image", response_model=DishDetail, summary="移除菜品图片")
def remove_dish_image(
    dish_id: UUID,
    session: Session = Depends(get_session),
    _: AuthUser = Depends(require_roles(*WRITE_ROLES)),
) -> DishDetail:
    dish = service.get_dish(session, dish_id)
    if not dish.is_active:
        raise BusinessRuleError("已停用的菜品不能修改图片")
    images.image_path(dish_id).unlink(missing_ok=True)
    return service.get_dish_detail(session, dish_id)

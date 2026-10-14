"""菜单推荐接口。

推荐只作为建议：生成与查看对三个角色开放，**采纳与否决只给能对菜单负责的角色**，
而且否决必须写明原因——需求里写明它会被用来改进后续推荐。
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.modules.auth.dependencies import require_roles
from app.modules.auth.schemas import AuthUser
from app.modules.recommendation import service
from app.modules.recommendation.schemas import (
    DecideRequest,
    MenuSuggestionRead,
    SuggestionSummary,
)
from app.shared.enums import MealType, UserRole

router = APIRouter(prefix="/recommendation", tags=["菜单推荐"])

WRITE_ROLES = (UserRole.RECORDER, UserRole.CANTEEN_ADMIN)
VIEW_ROLES = (UserRole.RECORDER, UserRole.CANTEEN_ADMIN, UserRole.SCHOOL_ADMIN)


@router.post("/generate", response_model=MenuSuggestionRead, summary="生成一份菜单建议")
def generate(
    on_date: date = Query(description="要推荐的日期"),
    meal_type: MealType = Query(default=MealType.LUNCH),
    diner_count: int | None = Query(default=None, ge=1, description="不填则用最近一次采集的人次"),
    session: Session = Depends(get_session),
    _: AuthUser = Depends(require_roles(*WRITE_ROLES)),
) -> MenuSuggestionRead:
    return service.generate(session, on_date=on_date, meal_type=meal_type, diner_count=diner_count)


@router.get("", response_model=list[SuggestionSummary], summary="查询历史推荐")
def list_suggestions(
    on_date: date | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
    _: AuthUser = Depends(require_roles(*VIEW_ROLES)),
) -> list[SuggestionSummary]:
    return service.list_suggestions(session, on_date=on_date, limit=limit)


@router.get("/{suggestion_id}", response_model=MenuSuggestionRead, summary="查看某份推荐")
def get_suggestion(
    suggestion_id: UUID,
    session: Session = Depends(get_session),
    _: AuthUser = Depends(require_roles(*VIEW_ROLES)),
) -> MenuSuggestionRead:
    return service.get_suggestion(session, suggestion_id)


@router.post("/{suggestion_id}/decide", response_model=MenuSuggestionRead, summary="采纳或否决")
def decide(
    suggestion_id: UUID,
    payload: DecideRequest,
    session: Session = Depends(get_session),
    actor: AuthUser = Depends(require_roles(*WRITE_ROLES)),
) -> MenuSuggestionRead:
    return service.decide(session, suggestion_id=suggestion_id, payload=payload, actor_id=actor.id)

"""公开大屏接口。

**免登录**：这是全系统唯一不校验身份的接口，只暴露菜品级营养与群体级聚合数据，
不含任何个人相关信息。需求文档里的「学生端」指的就是这一屏。
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.modules.public import service
from app.modules.public.schemas import PublicBoard
from app.shared.enums import MealType

router = APIRouter(prefix="/public", tags=["公开大屏（免登录）"])


@router.get(
    "/board/today",
    response_model=PublicBoard,
    summary="今日菜单与营养（免登录）",
)
def read_board(
    on_date: date | None = Query(
        default=None,
        description="指定日期，默认取业务时区的今天；便于回看与功能验证",
    ),
    meal_type: MealType | None = Query(
        default=None,
        description="指定餐次；不传时保持原有主餐次选择（午餐优先）",
    ),
    session: Session = Depends(get_session),
) -> PublicBoard:
    return service.build_board(session, on_date=on_date, meal_type=meal_type)

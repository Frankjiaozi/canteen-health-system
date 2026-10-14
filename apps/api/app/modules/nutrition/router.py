"""三层校准接口。

第二层（当日闭环）与第三层（抽样纠偏）的入口都在这里。校准结果与理论值**并存**，
分别用不同的 `value_type` 落库，不覆盖——这样界面上能把两个值摆在一起看，
而不是让人去猜「现在这个数到底是校准前还是校准后」。
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.modules.auth.dependencies import require_roles
from app.modules.auth.schemas import AuthUser
from app.modules.nutrition import repository, service
from app.modules.nutrition.models import CalibrationFactor
from app.modules.nutrition.schemas import (
    CalibrationFactorRead,
    ClosureFactorRead,
    ClosureRunResponse,
)
from app.shared.enums import MealType, SeasoningCategory, UserRole

router = APIRouter(prefix="/calibration", tags=["三层校准"])

#: 校准会改动营养结果，只允许能对数据负责的两个角色执行
RUN_ROLES = (UserRole.RECORDER, UserRole.CANTEEN_ADMIN)
VIEW_ROLES = (UserRole.RECORDER, UserRole.CANTEEN_ADMIN, UserRole.SCHOOL_ADMIN)


@router.post("/daily-closure", response_model=ClosureRunResponse, summary="执行当日闭环校准")
def run_daily_closure(
    on_date: date = Query(description="要校准的业务日期"),
    meal_type: MealType = Query(default=MealType.LUNCH),
    session: Session = Depends(get_session),
    _: AuthUser = Depends(require_roles(*RUN_ROLES)),
) -> ClosureRunResponse:
    report = service.compute_daily_closure(session, on_date=on_date, meal_type=meal_type)
    return ClosureRunResponse(
        date=report.date,
        meal_type=report.meal_type,
        meal_type_label=report.meal_type.label,
        factors=[
            ClosureFactorRead(
                cooking_method=row.cooking_method,
                cooking_method_label=row.cooking_method.label,
                coefficients=row.coefficients,
                coefficient_labels={
                    code: SeasoningCategory(code).label for code in row.coefficients
                },
                theoretical_g=row.theoretical_g,
                actual_g=row.actual_g,
            )
            for row in report.factors
        ],
        calibrated_rows=report.calibrated_rows,
        note=report.note,
    )


@router.get("/factors", response_model=list[CalibrationFactorRead], summary="查看已落库的校准系数")
def list_factors(
    on_date: date = Query(description="业务日期"),
    meal_type: MealType = Query(default=MealType.LUNCH),
    session: Session = Depends(get_session),
    _: AuthUser = Depends(require_roles(*VIEW_ROLES)),
) -> list[CalibrationFactorRead]:
    rows = repository.load_calibration_factors(session, on_date=on_date, meal_type=meal_type)
    return [_to_read(row) for row in rows]


def _to_read(row: CalibrationFactor) -> CalibrationFactorRead:
    return CalibrationFactorRead(
        date=row.date,
        meal_type=row.meal_type,
        meal_type_label=row.meal_type.label,
        cooking_method=row.cooking_method,
        cooking_method_label=row.cooking_method.label,
        source=row.source,
        source_label=row.source.label,
        coefficients={key: str(value) for key, value in row.coefficients.items()},
        dish_id=None if row.dish_id is None else str(row.dish_id),
        basis_note=row.basis_note,
    )

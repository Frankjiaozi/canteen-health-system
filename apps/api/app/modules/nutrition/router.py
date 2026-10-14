"""三层校准接口。

第二层（当日闭环）与第三层（抽样纠偏）的入口都在这里。校准结果与理论值**并存**，
分别用不同的 `value_type` 落库，不覆盖——这样界面上能把两个值摆在一起看，
而不是让人去猜「现在这个数到底是校准前还是校准后」。
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.db.session import get_session
from app.modules.auth.dependencies import require_roles
from app.modules.auth.schemas import AuthUser
from app.modules.dish import repository as dish_repository
from app.modules.nutrition import repository, service
from app.modules.nutrition.engine import NutrientVector
from app.modules.nutrition.models import CalibrationFactor, DishNutrition
from app.modules.nutrition.schemas import (
    CalibrationFactorRead,
    ClosureCheckRead,
    ClosureFactorRead,
    ClosureRunResponse,
    ClosureWindowRead,
    NutritionComparison,
    SampleCreate,
    SampleResult,
    SamplingCorrectionRead,
)
from app.shared.enums import (
    MealType,
    NutrientCaliber,
    NutritionValueType,
    SeasoningCategory,
    UserRole,
)
from app.shared.nutrients import NUTRIENT_FIELDS

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
                implied_g=row.implied_g,
                allocated_g=row.allocated_g,
            )
            for row in report.factors
        ],
        window=ClosureWindowRead(
            days=report.window.days,
            samples=report.window.samples,
            start=report.window.start,
            end=report.window.end,
            residual_mape=str(report.window.residual_mape),
            ridge=str(report.window.ridge),
            fallback_reason=report.window.fallback_reason,
        ),
        checks=[
            ClosureCheckRead(
                code=row.category.value,
                label=row.category.label,
                actual_g=str(row.actual_g),
                predicted_g=str(row.predicted_g),
                deviation=str(row.deviation),
                status=row.status,
            )
            for row in report.checks
        ],
        sampling_corrections=[
            SamplingCorrectionRead(
                dish_id=row.dish_id,
                dish_name=row.dish_name,
                overall=str(row.overall),
                scope=row.scope,
                scope_label="这道菜" if row.scope == "DISH" else "整类烹饪方式",
            )
            for row in report.sampling_corrections
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


@router.post("/samples", response_model=SampleResult, summary="录入抽样称重实测")
def create_sample(
    payload: SampleCreate,
    session: Session = Depends(get_session),
    actor: AuthUser = Depends(require_roles(*RUN_ROLES)),
) -> SampleResult:
    report = service.record_sample(
        session,
        dish_id=payload.dish_id,
        on_date=payload.date,
        meal_type=payload.meal_type,
        measured=NutrientVector(
            energy_kcal=payload.measured_energy_kcal,
            protein_g=payload.measured_protein_g,
            fat_g=payload.measured_fat_g,
            carb_g=payload.measured_carb_g,
            sodium_mg=payload.measured_sodium_mg,
        ),
        scope=payload.scope,
        note=payload.note,
        created_by=actor.id,
    )
    return SampleResult(
        dish_id=report.dish_id,
        dish_name=report.dish_name,
        date=report.on_date,
        meal_type=report.meal_type,
        meal_type_label=report.meal_type.label,
        measured=report.measured.as_trace(),
        computed=report.computed.as_trace(),
        deviations=report.deviations,
        overall_factor=None if report.overall_factor is None else str(report.overall_factor),
        applied=report.applied,
        suspect_recipe=report.suspect_recipe,
        note=report.note,
    )


@router.get("/comparison", response_model=NutritionComparison, summary="理论值/校准值/抽样值对比")
def compare(
    dish_id: UUID = Query(description="菜品 ID"),
    on_date: date = Query(description="业务日期"),
    meal_type: MealType = Query(default=MealType.LUNCH),
    session: Session = Depends(get_session),
    _: AuthUser = Depends(require_roles(*VIEW_ROLES)),
) -> NutritionComparison:
    dish = dish_repository.get(session, dish_id)
    if dish is None:
        raise NotFoundError("菜品不存在")

    def _value(value_type: NutritionValueType) -> dict[str, str] | None:
        row = session.scalar(
            select(DishNutrition)
            .where(
                DishNutrition.dish_id == dish_id,
                DishNutrition.date == on_date,
                DishNutrition.meal_type == meal_type,
                DishNutrition.caliber == NutrientCaliber.PER_SERVING,
                DishNutrition.value_type == value_type,
            )
            .limit(1)
        )
        return (
            None if row is None else {field: str(getattr(row, field)) for field in NUTRIENT_FIELDS}
        )

    return NutritionComparison(
        dish_id=dish_id,
        dish_name=dish.name,
        date=on_date,
        theoretical=_value(NutritionValueType.THEORETICAL),
        calibrated=_value(NutritionValueType.CALIBRATED),
        sampled=_value(NutritionValueType.SAMPLED),
    )

"""营养域的响应模型。

`StandardComparison` 放在营养域，因为膳食指南基准表归它所有；
公开大屏与管理端看板都复用它，保证同一个判断不会有两套实现。
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.shared.enums import CalibrationSource, CookingMethod, MealType


class StandardComparison(BaseModel):
    """实际值与膳食指南量化基准的对照。"""

    code: str
    label: str
    unit: str
    target_min: str | None = None
    target_max: str | None = None
    actual: str | None = Field(default=None, description="实际值；人均口径或种类数")
    status: str = Field(description="ok / over / under / unknown")
    source: str
    source_quote: str | None = None


class ClosureFactorRead(BaseModel):
    """一种烹饪方式下，油盐糖各自的校准系数与它的依据。"""

    cooking_method: CookingMethod
    cooking_method_label: str
    #: 类别代码 → 系数
    coefficients: dict[str, str]
    #: 类别代码 → 中文名
    coefficient_labels: dict[str, str]
    #: 类别代码 → 当日按配方推算的用量（克）
    theoretical_g: dict[str, str]
    #: 类别代码 → 当日实际用量（克）；不逐日采集的类别为空
    actual_g: dict[str, str | None]


class ClosureRunResponse(BaseModel):
    """一次当日闭环校准的结果。"""

    date: date
    meal_type: MealType
    meal_type_label: str
    factors: list[ClosureFactorRead]
    calibrated_rows: int = Field(description="本次写入的校准结果条数（单份 + 人均）")
    note: str = Field(description="口径说明，避免把校准值当成新一套真值")


class CalibrationFactorRead(BaseModel):
    """已落库的一条校准系数。"""

    date: date
    meal_type: MealType
    meal_type_label: str
    cooking_method: CookingMethod
    cooking_method_label: str
    source: CalibrationSource
    source_label: str
    coefficients: dict[str, str]
    dish_id: str | None = Field(default=None, description="针对单道菜的抽样纠偏才有值")
    basis_note: str | None = None


def to_comparison(
    *,
    code: str,
    label: str,
    unit: str,
    target_min: str | None,
    target_max: str | None,
    actual: str | None,
    status: str,
    source: str,
    source_quote: str | None,
) -> StandardComparison:
    return StandardComparison(
        code=code,
        label=label,
        unit=unit,
        target_min=target_min,
        target_max=target_max,
        actual=actual,
        status=status,
        source=source,
        source_quote=source_quote,
    )

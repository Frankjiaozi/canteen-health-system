"""营养域的响应模型。

`StandardComparison` 放在营养域，因为膳食指南基准表归它所有；
公开大屏与管理端看板都复用它，保证同一个判断不会有两套实现。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

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
    """一种烹饪方式下，调料各自的校准系数与它的依据。"""

    cooking_method: CookingMethod
    cooking_method_label: str
    #: 类别代码 → 系数（由窗口内历史拟合得出）
    coefficients: dict[str, str]
    #: 类别代码 → 中文名
    coefficient_labels: dict[str, str]
    #: 类别代码 → 当日该烹饪方式按配方推算的用量（克）
    implied_g: dict[str, str]
    #: 类别代码 → 按系数分摊到该烹饪方式的用量（克）
    allocated_g: dict[str, str]


class ClosureWindowRead(BaseModel):
    """这次拟合用的是什么窗口、解得稳不稳——系数脱离窗口就没有意义。"""

    days: int
    samples: int = Field(description="窗口内实际参与拟合的采集次数")
    start: date | None = None
    end: date
    residual_mape: str = Field(description="各次采集相对误差的平均绝对值")
    ridge: str = Field(description="岭项相对强度，罚向 1 而不是罚向 0")
    fallback_reason: str | None = Field(
        default=None, description="退化成整餐统一比值时的原因；正常拟合时为空"
    )


class ClosureCheckRead(BaseModel):
    """当天实际总量与拟合预测的对照。"""

    code: str
    label: str
    actual_g: str
    predicted_g: str
    deviation: str
    status: str = Field(description="ok / warn")


class SamplingCorrectionRead(BaseModel):
    """第三层抽样纠偏作用到某道菜上的整体修正比。"""

    dish_id: UUID
    dish_name: str
    overall: str
    scope: str = Field(description="DISH = 只针对这道菜；COOKING_METHOD = 针对整类烹饪方式")
    scope_label: str


class ClosureRunResponse(BaseModel):
    """一次当日闭环校准的结果。"""

    date: date
    meal_type: MealType
    meal_type_label: str
    factors: list[ClosureFactorRead]
    window: ClosureWindowRead
    #: 当天总量与拟合预测的对照；当天总量是校验项，不是乘数
    checks: list[ClosureCheckRead]
    #: 本次叠加到菜品上的第三层抽样修正；没有抽样记录时为空数组
    sampling_corrections: list[SamplingCorrectionRead]
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


class SampleCreate(BaseModel):
    """抽样称重实测的录入内容。数值都是**单份**口径。"""

    model_config = ConfigDict(extra="forbid")

    dish_id: UUID
    date: date
    meal_type: MealType = MealType.LUNCH
    measured_energy_kcal: Decimal = Field(ge=0)
    measured_protein_g: Decimal = Field(ge=0)
    measured_fat_g: Decimal = Field(ge=0)
    measured_carb_g: Decimal = Field(ge=0)
    measured_sodium_mg: Decimal = Field(ge=0)
    #: DISH = 只修正这一道菜；COOKING_METHOD = 修正这类烹饪方式
    scope: Literal["DISH", "COOKING_METHOD"] = "DISH"
    note: str | None = Field(default=None, max_length=255)


class SampleResult(BaseModel):
    dish_id: UUID
    dish_name: str
    date: date
    meal_type: MealType
    meal_type_label: str
    measured: dict[str, str]
    computed: dict[str, str]
    deviations: dict[str, str]
    overall_factor: str | None = Field(description="由能量反推出的调味料整体系数")
    applied: bool = Field(description="系数是否已生效")
    suspect_recipe: bool = Field(description="实测偏差是否大到不像调味料问题")
    note: str


class NutritionComparison(BaseModel):
    """同一道菜的三个口径来源并排——理论、校准、抽样实测。"""

    dish_id: UUID
    dish_name: str
    date: date
    theoretical: dict[str, str] | None = None
    calibrated: dict[str, str] | None = None
    sampled: dict[str, str] | None = None


class SamplingCandidate(BaseModel):
    """抽样页上的一道候选菜：理论值、校准值、已录的实测值并排。"""

    dish_id: UUID
    dish_name: str
    category_label: str
    cooking_method_label: str
    theoretical: dict[str, str] | None = None
    calibrated: dict[str, str] | None = None
    sampled: dict[str, str] | None = None
    #: 已经有实测值时，顺带把当时的结论带回来（是否套用了系数、是否疑似配方有误）
    applied: bool | None = None
    suspect_recipe: bool | None = None


class SamplingCandidates(BaseModel):
    """某天某一餐全部候选菜。"""

    date: date
    meal_type: MealType
    meal_type_label: str
    menu_confirmed: bool
    dishes: list[SamplingCandidate]
    #: 最近一次抽样纠偏留下的系数，便于判断当前脚下踩的是什么
    recent_corrections: list[SamplingCorrectionRead]


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

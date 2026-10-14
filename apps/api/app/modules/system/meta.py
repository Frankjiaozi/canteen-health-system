"""元数据接口：把枚举取值与中文文案下发给前端。

前端不该再抄一份类别、烹饪方式的中文映射——那是最容易和后台悄悄不一致的地方。
这里的内容直接由 `app/shared/enums.py` 的 `ENUM_LABELS` 生成，只有一处真源。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.modules.auth.dependencies import require_roles
from app.modules.auth.schemas import AuthUser
from app.shared.enums import (
    MANUAL_ANOMALY_FLAGS,
    AnomalyFlag,
    CookingMethod,
    DishCategory,
    IngredientCategory,
    LabelledStrEnum,
    MealType,
    SeasoningCategory,
    StandardCode,
    UserRole,
)

router = APIRouter(prefix="/meta", tags=["元数据"])


class EnumOption(BaseModel):
    value: str = Field(description="稳定代码，落库与接口传输都用它")
    label: str = Field(description="中文展示名")


class EnumOptions(BaseModel):
    ingredient_category: list[EnumOption]
    dish_category: list[EnumOption]
    cooking_method: list[EnumOption]
    meal_type: list[EnumOption]
    seasoning_category: list[EnumOption]
    user_role: list[EnumOption]
    standard_code: list[EnumOption]
    #: 全部异常标记，用于把库里存下的代码渲染成中文
    anomaly_flag: list[EnumOption]
    #: 其中由录入员勾选的那三个；系统回写的不在列
    manual_anomaly_flag: list[EnumOption]


def _options(enum_cls: type[LabelledStrEnum]) -> list[EnumOption]:
    return [EnumOption(value=member.value, label=member.label) for member in enum_cls]


@router.get("/enums", response_model=EnumOptions, summary="枚举取值与中文文案")
def list_enum_options(
    _: AuthUser = Depends(
        require_roles(UserRole.RECORDER, UserRole.CANTEEN_ADMIN, UserRole.SCHOOL_ADMIN)
    ),
) -> EnumOptions:
    return EnumOptions(
        ingredient_category=_options(IngredientCategory),
        dish_category=_options(DishCategory),
        cooking_method=_options(CookingMethod),
        meal_type=_options(MealType),
        seasoning_category=_options(SeasoningCategory),
        user_role=_options(UserRole),
        standard_code=_options(StandardCode),
        anomaly_flag=_options(AnomalyFlag),
        manual_anomaly_flag=[
            EnumOption(value=member.value, label=member.label) for member in MANUAL_ANOMALY_FLAGS
        ],
    )

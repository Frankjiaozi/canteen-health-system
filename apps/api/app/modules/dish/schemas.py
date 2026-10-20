"""菜品与配方的请求与响应模型。"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.shared.enums import CookingMethod, DishCategory

#: 字段名与类型同名时，Pydantic 解析注解用的是「模块全局 + 类命名空间」，
#: 于是 `date: date | None = Field(...)` 会读到类里那个默认值，报 FieldInfo | None。
#: 这里给日期类型留一个别名，绕开同名冲突（`datetime.date` 也不行：
#: 在类 `datetime` 上取 `.date` 拿到的是同名方法）。
DateType = date


class RecipeIngredientLine(BaseModel):
    """配方里的一行食材。"""

    model_config = ConfigDict(extra="forbid")

    ingredient_id: UUID
    quantity_per_serving_g: Decimal = Field(gt=0, description="单份用量（克，市品重量）")
    edible_ratio_override: Decimal | None = Field(
        default=None, ge=0, le=1, description="覆盖食材库默认可食部比例"
    )
    note: str | None = Field(default=None, max_length=255)


class RecipeSeasoningLine(BaseModel):
    """配方里的一行调味料分摊量。"""

    model_config = ConfigDict(extra="forbid")

    seasoning_id: UUID
    quantity_per_serving_g: Decimal = Field(gt=0, description="单份用量（克）")
    note: str | None = Field(default=None, max_length=255)


class RecipePayload(BaseModel):
    """整份配方。维护方式为整体替换，不做逐行增删。"""

    model_config = ConfigDict(extra="forbid")

    ingredients: list[RecipeIngredientLine] = Field(
        min_length=1, description="至少要有一行食材，否则算不出营养"
    )
    seasonings: list[RecipeSeasoningLine] = Field(default_factory=list)

    @field_validator("ingredients")
    @classmethod
    def _no_duplicate_ingredient(
        cls, value: list[RecipeIngredientLine]
    ) -> list[RecipeIngredientLine]:
        ids = [line.ingredient_id for line in value]
        if len(set(ids)) != len(ids):
            raise ValueError("同一道菜里食材不能重复")
        return value

    @field_validator("seasonings")
    @classmethod
    def _no_duplicate_seasoning(cls, value: list[RecipeSeasoningLine]) -> list[RecipeSeasoningLine]:
        ids = [line.seasoning_id for line in value]
        if len(set(ids)) != len(ids):
            raise ValueError("同一道菜里调味料不能重复")
        return value


class DishBase(BaseModel):
    name: str = Field(min_length=1, max_length=64, description="菜品名称")
    category: DishCategory = Field(description="菜品类别")
    cooking_method: CookingMethod = Field(description="烹饪方式")
    standard_serving_g: Decimal = Field(gt=0, description="标准份量（克）")
    servings_per_pot: Decimal = Field(gt=0, description="单锅制作份数")
    allergens: list[str] = Field(default_factory=list, description="过敏原标记")
    is_breakfast_staple: bool = Field(
        default=False,
        description=(
            "早餐固定供应：勾了的菜构成每天的早餐（不走推荐求解），并且不再进入午餐与晚餐的候选池"
        ),
    )
    note: str | None = Field(default=None, max_length=255)


class DishCreate(DishBase):
    """新建菜品时可一并提交配方，省掉一次往返。"""

    recipe: RecipePayload | None = None


class DishUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=64)
    category: DishCategory | None = None
    cooking_method: CookingMethod | None = None
    standard_serving_g: Decimal | None = Field(default=None, gt=0)
    servings_per_pot: Decimal | None = Field(default=None, gt=0)
    allergens: list[str] | None = None
    is_breakfast_staple: bool | None = None
    note: str | None = Field(default=None, max_length=255)


class RecipeIngredientRead(BaseModel):
    ingredient_id: UUID
    ingredient_name: str
    ingredient_active: bool
    quantity_per_serving_g: str
    edible_ratio_override: str | None
    unit_price: str | None
    energy_kcal: str | None
    protein_g: str | None
    fat_g: str | None
    carb_g: str | None
    sodium_mg: str | None
    note: str | None


class RecipeSeasoningRead(BaseModel):
    seasoning_id: UUID
    seasoning_name: str
    seasoning_active: bool
    quantity_per_serving_g: str
    unit_price: str | None
    note: str | None


class RecipeRead(BaseModel):
    ingredients: list[RecipeIngredientRead]
    seasonings: list[RecipeSeasoningRead]


class NutritionSummary(BaseModel):
    """列表里展示的单份营养摘要。

    `date` 有值表示读的是落库快照，它属于某一餐；这道菜要是从没被排进过菜单，
    数值就是按当前配方现算的预览，不属于任何一天，因此 `date` 为空。
    """

    date: DateType | None = Field(default=None, description="所属日期；按当前配方现算的预览为空")
    value_type: str
    energy_kcal: str
    protein_g: str
    fat_g: str
    carb_g: str
    sodium_mg: str


class DishRead(DishBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    image_url: str | None = Field(default=None, description="用户上传的菜品图片；未上传时为空")
    recipe_version: int
    is_active: bool
    category_label: str
    cooking_method_label: str
    nutrition: NutritionSummary | None = Field(
        default=None, description="最近一次算出的单份营养；尚未计算时为空"
    )
    created_at: datetime
    updated_at: datetime


class DishDetail(DishRead):
    recipe: RecipeRead


class DishPage(BaseModel):
    items: list[DishRead]
    total: int
    page: int
    page_size: int


class RecipeUpdateResult(BaseModel):
    dish: DishDetail
    recipe_version: int = Field(description="配方版本，每次保存递增")
    recomputed_rows: int = Field(description="同步重算的营养结果条数")

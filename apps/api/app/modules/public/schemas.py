"""公开大屏的响应模型。

数值一律以字符串下发（与其它接口的 Decimal 口径一致），避免浮点误差进入展示层。
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.nutrition.schemas import StandardComparison


class NutrientValue(BaseModel):
    """一项营养指标：数值 + 单位 + 上下界。"""

    code: str = Field(description="营养素代码，例如 ENERGY")
    label: str = Field(description="中文名")
    unit: str = Field(description="单位")
    digits: int = Field(description="展示小数位")
    value: str = Field(description="单份数值")
    lower: str = Field(description="误差下界")
    upper: str = Field(description="误差上界")


class PublicDishCard(BaseModel):
    """一道菜的营养卡。口径固定为「单份」。"""

    dish_id: UUID
    name: str
    category_label: str
    cooking_method_label: str
    standard_serving_g: str = Field(description="标准份量（克）")
    # 这两个字段接口总会返回，因此不设默认值——设了默认值会在 OpenAPI 里变成可选，
    # 前端就得处处兜底，反而不如把契约写准
    allergens: list[str] = Field(description="过敏原标记，无则为空数组")
    nutrients: list[NutrientValue]
    recipe_version: int
    source_note: str | None = Field(default=None, description="数值来源说明")
    missing_nutrients: list[str] = Field(description="成分数据缺失项，无则为空数组")


class PublicBoard(BaseModel):
    """公开大屏的全部内容。"""

    date: date
    meal_label: str = Field(description="餐次中文名")
    generated_at: datetime
    diner_count: int | None = Field(default=None, description="就餐人次")
    dishes: list[PublicDishCard]
    standards: list[StandardComparison]
    disclaimer: str = Field(description="合规说明")

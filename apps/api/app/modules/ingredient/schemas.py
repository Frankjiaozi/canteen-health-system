"""食材库的请求与响应模型。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.shared.enums import IngredientCategory


class IngredientBase(BaseModel):
    """食材的公共字段。营养成分统一以每 100 克可食部计。"""

    name: str = Field(min_length=1, max_length=64, description="食材名称")
    category: IngredientCategory = Field(description="食材类别")

    # 五项成分允许为空：食物成分表里确实有缺项，写成 0 会造成静默失真
    energy_kcal: Decimal | None = Field(default=None, ge=0, description="能量（千卡/100g）")
    protein_g: Decimal | None = Field(default=None, ge=0, description="蛋白质（克/100g）")
    fat_g: Decimal | None = Field(default=None, ge=0, description="脂肪（克/100g）")
    carb_g: Decimal | None = Field(default=None, ge=0, description="碳水化合物（克/100g）")
    sodium_mg: Decimal | None = Field(default=None, ge=0, description="钠（毫克/100g）")

    edible_ratio: Decimal = Field(
        default=Decimal("1.0"), ge=0, le=1, description="可食部比例（0~1）"
    )
    unit_price: Decimal | None = Field(default=None, ge=0, description="单价（元/千克）")

    data_source: str = Field(min_length=1, max_length=128, description="数据来源，必须可追溯")
    source_version: str | None = Field(default=None, max_length=64, description="来源版本")
    note: str | None = Field(default=None, max_length=255)


class IngredientCreate(IngredientBase):
    pass


class IngredientUpdate(BaseModel):
    """局部更新：只提交需要改的字段。"""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=64)
    category: IngredientCategory | None = None
    energy_kcal: Decimal | None = Field(default=None, ge=0)
    protein_g: Decimal | None = Field(default=None, ge=0)
    fat_g: Decimal | None = Field(default=None, ge=0)
    carb_g: Decimal | None = Field(default=None, ge=0)
    sodium_mg: Decimal | None = Field(default=None, ge=0)
    edible_ratio: Decimal | None = Field(default=None, ge=0, le=1)
    unit_price: Decimal | None = Field(default=None, ge=0)
    data_source: str | None = Field(default=None, min_length=1, max_length=128)
    source_version: str | None = Field(default=None, max_length=64)
    note: str | None = Field(default=None, max_length=255)


class IngredientRead(IngredientBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    is_active: bool
    # 中文类别随响应下发，前端不必再维护一份文案映射
    category_label: str
    created_at: datetime
    updated_at: datetime


class IngredientPage(BaseModel):
    """统一分页结构。"""

    items: list[IngredientRead]
    total: int
    page: int
    page_size: int

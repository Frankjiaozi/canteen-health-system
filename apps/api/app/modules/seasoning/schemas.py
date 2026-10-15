"""调味料库的请求与响应模型。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.shared.enums import SeasoningCategory


class SeasoningBase(BaseModel):
    """调味料的公共字段。营养成分统一以每 100 克计，与食材库同一口径。"""

    name: str = Field(min_length=1, max_length=64, description="调味料名称")
    category: SeasoningCategory = Field(description="调味料类别")
    unit: str = Field(default="g", min_length=1, max_length=16, description="计量单位")

    # 允许为空：与食材库同理，缺项要保持缺失而不是写成 0
    energy_kcal: Decimal | None = Field(default=None, ge=0)
    protein_g: Decimal | None = Field(default=None, ge=0)
    fat_g: Decimal | None = Field(default=None, ge=0)
    carb_g: Decimal | None = Field(default=None, ge=0)
    sodium_mg: Decimal | None = Field(default=None, ge=0)

    unit_price: Decimal | None = Field(default=None, ge=0, description="单价（元/千克）")
    data_source: str | None = Field(default=None, max_length=128)
    source_version: str | None = Field(
        default=None, max_length=64, description="来源版本，例如「豆油 · 条目 1497」"
    )
    note: str | None = Field(default=None, max_length=255)


class SeasoningCreate(SeasoningBase):
    pass


class SeasoningUpdate(BaseModel):
    """局部更新：只提交需要改的字段。"""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=64)
    category: SeasoningCategory | None = None
    unit: str | None = Field(default=None, min_length=1, max_length=16)
    energy_kcal: Decimal | None = Field(default=None, ge=0)
    protein_g: Decimal | None = Field(default=None, ge=0)
    fat_g: Decimal | None = Field(default=None, ge=0)
    carb_g: Decimal | None = Field(default=None, ge=0)
    sodium_mg: Decimal | None = Field(default=None, ge=0)
    unit_price: Decimal | None = Field(default=None, ge=0)
    data_source: str | None = Field(default=None, max_length=128)
    source_version: str | None = Field(default=None, max_length=64)
    note: str | None = Field(default=None, max_length=255)


class SeasoningRead(SeasoningBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    is_active: bool
    # 中文类别随响应下发，前端不必再维护一份文案映射
    category_label: str
    created_at: datetime
    updated_at: datetime


class SeasoningPage(BaseModel):
    items: list[SeasoningRead]
    total: int
    page: int
    page_size: int

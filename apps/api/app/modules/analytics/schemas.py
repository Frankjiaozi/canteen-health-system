"""管理端看板的响应模型。

数值统一以字符串下发，与其它接口的 Decimal 口径一致。
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.modules.nutrition.schemas import StandardComparison


class StandardTarget(BaseModel):
    """图表画目标线用的基准。"""

    code: str
    label: str
    unit: str
    target_min: str | None = None
    target_max: str | None = None


class TrendPoint(BaseModel):
    """某一天的油盐糖用量。"""

    date: date
    diner_count: int
    oil_total_g: str
    salt_total_g: str
    sugar_total_g: str
    oil_per_capita_g: str
    salt_per_capita_g: str
    sugar_per_capita_g: str


class TrendsResponse(BaseModel):
    days: int
    start: date
    end: date
    points: list[TrendPoint]
    targets: list[StandardTarget]


class NutrientAmount(BaseModel):
    code: str
    label: str
    unit: str
    digits: int
    value: str | None = None


class PerCapitaResponse(BaseModel):
    days: int
    start: date
    end: date
    latest_date: date | None = None
    latest_diner_count: int | None = None
    latest: list[NutrientAmount]
    average: list[NutrientAmount]
    comparisons: list[StandardComparison]
    basis_note: str = Field(description="数值口径说明，避免把不同来源的数字混着解读")


class CompliancePoint(BaseModel):
    date: date
    compliant: int
    total: int
    rate: str
    items: list[StandardComparison]


class ComplianceResponse(BaseModel):
    days: int
    start: date
    end: date
    points: list[CompliancePoint]
    overall_rate: str | None = None


class WastePoint(BaseModel):
    date: date
    produced_weight_g: str
    leftover_weight_g: str
    waste_ratio: str


class WasteResponse(BaseModel):
    days: int
    start: date
    end: date
    points: list[WastePoint]
    average_ratio: str | None = None


class DashboardSummary(BaseModel):
    days: int
    start: date
    end: date
    days_with_records: int
    avg_diner_count: int
    avg_salt_per_capita_g: str | None = None
    avg_oil_per_capita_g: str | None = None
    avg_added_sugar_per_capita_g: str | None = None
    avg_waste_ratio: str | None = None
    avg_dish_variety: str | None = None
    latest_compliance_rate: str | None = None

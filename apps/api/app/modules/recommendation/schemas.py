"""菜单推荐的请求与响应模型。"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.shared.enums import MealType, SuggestionStatus


class PlannedDishRead(BaseModel):
    dish_id: str
    dish_name: str
    category_label: str
    cooking_method_label: str
    #: 这一道菜的成本（元）。份数不在这里——推荐只回答「做哪几道菜」，
    #: 份数由预测给出，见 menu-plan 接口
    cost: str = Field(description="这道菜的成本（元）")
    #: 单位：单份营养与调料用量，便于核对为什么选了它
    energy_kcal: str
    salt_g: str
    popularity: str
    #: 这份单份营养取自哪一层（抽样实测 / 校准 / 配方推算）
    nutrition_basis: str = ""


class NutrientGap(BaseModel):
    """与目标的差距。**缺口多大**要写出来，只给「达标 / 不达标」的标签不算完成。"""

    code: str
    label: str
    unit: str
    target_text: str
    actual: str
    status: str = Field(description="ok / over / under")
    gap: str = Field(description="缺口；达标时为 0")
    note: str | None = None


class SuggestionReason(BaseModel):
    """一条推荐理由。厨师长不信任不解释的黑箱建议，所以每条都要说得出原因。"""

    kind: str = Field(description="nutrition / cost / popularity / constraint / variety")
    text: str


class MenuSuggestionRead(BaseModel):
    id: str
    date: date
    meal_type: MealType
    meal_type_label: str
    status: SuggestionStatus
    status_label: str
    dishes: list[PlannedDishRead]
    gaps: list[NutrientGap]
    reasons: list[SuggestionReason]
    cost_estimate: str
    budget: str
    diner_count: int
    #: 目标区间是怎么来的（能量目标待核实、油盐糖取每日上限等）
    target_basis: dict[str, object]
    binding: list[str]
    solver_status: str
    #: 因为「不连续两日重复」被排除的菜
    excluded_dishes: list[str]
    #: 有食材缺单价，成本因此偏低——要如实说出来
    missing_price_warning: str | None = None
    rejected_reason: str | None = None
    decided_at: datetime | None = None


class DecideRequest(BaseModel):
    status: SuggestionStatus = Field(description="ACCEPTED 采纳 / REJECTED 否决")
    reason: str | None = Field(default=None, max_length=255)


class SuggestionSummary(BaseModel):
    id: str
    date: date
    meal_type: MealType
    meal_type_label: str
    status: SuggestionStatus
    status_label: str
    dish_count: int
    cost_estimate: str
    created_at: datetime
    rejected_reason: str | None = None

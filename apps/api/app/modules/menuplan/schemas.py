"""「明日菜单与采购」的响应模型。

它把推荐、预测、采购三件事合成一份可读的结果，但**不自己造数**：
每一项都来自对应域，这一层只负责把它们对齐到同一批菜上。
"""

from __future__ import annotations

from datetime import date

from app.modules.forecast.schemas import IngredientRequirement
from app.modules.recommendation.schemas import NutrientGap, SuggestionReason
from app.shared.enums import MealType
from pydantic import BaseModel, Field


class MenuPlanDish(BaseModel):
    """推荐入选的一道菜，附上它明天的预测份数。"""

    dish_id: str
    dish_name: str
    category_label: str
    cooking_method_label: str
    #: 单份营养与调料用量，便于核对它为什么入选
    energy_kcal: str
    salt_g: str
    popularity: str
    nutrition_basis: str
    #: 明天的预测份数。预测不出来时为空，采购按基准份数算。
    predicted_servings: str | None = None
    predicted_basis_label: str | None = None
    #: 真 = 这道菜历史不足、预测不出来，采购用的是基准份数
    prediction_fallback: bool = False


class MenuPlanResponse(BaseModel):
    date: date
    meal_type: MealType
    meal_type_label: str
    diner_count: int
    suggestion_id: str
    dishes: list[MenuPlanDish]
    gaps: list[NutrientGap]
    reasons: list[SuggestionReason]
    requirements: list[IngredientRequirement]
    total_cost: str | None = None
    budget: str
    #: 目标区间是怎么来的（能量目标待核实、油盐糖取每日上限等），页面上要照实标注
    target_basis: dict[str, object]
    #: 有食材缺单价，金额因此偏低——要如实说出来
    missing_price_warning: str | None = None
    #: 因为「不连续两日重复」被排除的菜
    excluded_dishes: list[str]
    calendar_notes: list[str]
    #: 历史不足、预测不出来的菜（它们不会入选推荐）
    skipped_predictions: list[str]
    #: 采购量按什么份数算的——这一句必须写清楚，否则看的人不知道买多少是怎么来的
    servings_note: str
    notes: list[str]


class MenuPlanSyncResult(BaseModel):
    """「同步至当日数据」的结果。"""

    date: date
    meal_type: MealType
    meal_type_label: str
    suggestion_id: str
    dish_count: int
    #: 写入了多少条营养结果（每道菜一条单份理论值）
    nutrition_rows: int
    planned_servings_filled: int = Field(
        description="有几道菜带上了计划份数；预测不出来的菜为空，不编数"
    )
    message: str

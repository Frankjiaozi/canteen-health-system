"""「明日菜单与采购」的响应模型。

它把推荐、预测、采购三件事合成一份可读的结果，但**不自己造数**：
每一项都来自对应域，这一层只负责把它们对齐到同一批菜上。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from app.modules.forecast.schemas import IngredientRequirement
from app.modules.recommendation.schemas import NutrientGap, SuggestionReason
from app.shared.enums import MealType
from pydantic import BaseModel, ConfigDict, Field


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
    planned_servings: str | None = None


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
    snapshot_token: str = ""
    expected_menu_token: str = ""
    budget_per_person: str = ""
    requested_excluded_dish_ids: list[str] = Field(default_factory=list)
    calculation_version: str | None = None


class DailyMenuPlanResponse(BaseModel):
    """同一天早/午/晚三餐的合并结果。"""

    date: date
    meals: list[MenuPlanResponse]
    requirements: list[IngredientRequirement]
    total_cost: str | None = None
    budget: str
    servings_note: str
    fallback_dishes: list[str] = Field(default_factory=list)
    notes: list[str]
    suggestion_ids: dict[str, str]
    calculation_version: str | None = None


class MenuPlanConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    excluded_dish_ids: list[UUID] = Field(default_factory=list, max_length=50)
    budget_per_person: Decimal | None = Field(
        default=None, gt=0, le=1000, max_digits=8, decimal_places=2
    )


class PublishPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_token: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_menu_token: str = Field(pattern=r"^[a-f0-9]{64}$")


class PublishPlanReceipt(BaseModel):
    suggestion_id: str
    menu_day_id: str
    on_date: date
    meal_type: MealType
    dish_count: int
    published_at: str
    published_by: str
    already_published: bool = False


class UndoPlanReceipt(BaseModel):
    """撤回一次已发布方案的回执。原发布回执不删，只标记撤回，供审计。"""

    suggestion_id: str
    on_date: date
    meal_type: MealType
    meal_type_label: str
    undone_at: str
    undone_by: str


class ReadinessIssue(BaseModel):
    code: str
    severity: Literal["blocking", "warning"]
    title: str
    detail: str
    action: str
    link: str
    entity_id: str | None = None


class ReadinessCategory(BaseModel):
    code: str
    label: str
    available_count: int
    required_minimum: int


class PlanReadiness(BaseModel):
    checked_at: str
    on_date: date
    meal_type: MealType
    meal_type_label: str
    state: Literal["blocked", "attention", "ready"]
    active_dish_count: int
    candidate_count: int
    available_count: int
    excluded_count: int
    predicted_count: int
    history_start: date
    history_end: date
    history_record_count: int
    days_with_records: int
    latest_record_date: date | None
    latest_diner_count: int | None
    #: 系统按同星期历史和日历预测的就餐人次；与「最近一条记录」分开，
    #: 后者只是参考，不能直接当明天的规模。
    predicted_diner_count: int | None = None
    diner_count_lower: int | None = None
    diner_count_upper: int | None = None
    diner_count_basis: str | None = None
    diner_count_basis_label: str | None = None
    missing_price_count: int
    missing_nutrition_count: int
    categories: list[ReadinessCategory]
    issues: list[ReadinessIssue]
    issue_count: int
    truncated: bool = False
    note: str


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


class MenuPlanBatchDay(BaseModel):
    """批量排菜单里的一天。"""

    date: date
    #: GENERATED 已生成 / IMPORTED 已导入 / SKIPPED 跳过 / FAILED 排不出来
    status: str
    status_label: str
    reason: str | None = None
    suggestion_id: str | None = None
    dish_names: list[str] = Field(default_factory=list)
    dish_count: int = 0
    diner_count: int = 0
    #: 这一餐的采购金额（元）与摊到每个人头上的成本
    total_cost: str | None = None
    cost_per_person: str | None = None
    requirements_count: int = 0
    #: 这一天是不是放假/调休，来自节假日日历
    calendar_note: str | None = None
    #: 导入时写了几条营养结果
    nutrition_rows: int = 0


class MenuPlanBatchResult(BaseModel):
    start_date: date
    end_date: date
    meal_type: MealType
    meal_type_label: str
    days: int
    generated: int = 0
    imported: int = 0
    skipped: int = 0
    failed: int = 0
    rows: list[MenuPlanBatchDay]
    message: str


class MenuPlanBatchSyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggestion_ids: dict[date, UUID] = Field(
        max_length=31, description="用户已核对的逐日方案 ID；没有选定方案的日期跳过"
    )


class MenuPlanHistoryItem(BaseModel):
    created_at: datetime
    status_label: str
    plan: MenuPlanResponse

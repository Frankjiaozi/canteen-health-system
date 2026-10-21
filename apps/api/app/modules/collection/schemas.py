"""每日采集的请求与响应模型。"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.shared.enums import AnomalyFlag, MealType, PackageCode


class LoggedDish(BaseModel):
    """采集单里的一道菜。"""

    dish_id: str
    name: str
    package_codes: list[PackageCode] = Field(default_factory=lambda: [PackageCode.COMMON])
    package_labels: list[str] = Field(default_factory=lambda: [PackageCode.COMMON.label])
    is_shared: bool = False
    category_label: str
    cooking_method_label: str
    #: 是否已确认为当餐供应的菜。当天还没有菜单时，整份菜品库都会列出来供勾选
    selected: bool = False
    #: 是否在当天的菜单上（计划供应）。取消勾选后它仍然是「本来计划的菜」
    is_planned: bool = False
    #: 计划做多少份。由「明日菜单与采购」同步过来，采集提交后仍然留着，便于计划与实际对账
    planned_servings: str | None = None
    #: 已保存的出餐份数；还没录入时为空
    servings_produced: str | None = None
    leftover_ratio: str | None = Field(default=None, description="剩余比例 0~1")
    leftover_weight_g: str | None = None
    is_substituted: bool = False
    substitution_note: str | None = None
    #: 这道菜当天已有的单份营养结果（理论/校准/抽样中证据最强的一份），用于录入时对照
    energy_kcal: str | None = None
    nutrition_source: str | None = Field(default=None, description="数值来自哪一层")


class AnomalyRead(BaseModel):
    value: str
    label: str
    #: 由系统回写的标记不能人工取消，需要在界面上区分开
    system: bool


class DailyLogSheet(BaseModel):
    """某个日期 + 餐次的采集单。没保存过时除菜品清单外都是空值。"""

    date: date
    meal_type: MealType
    meal_type_label: str
    #: 是否已经保存过
    saved: bool
    submitted_at: datetime | None = None
    diner_count: int | None = None
    oil_total_g: str | None = None
    salt_total_g: str | None = None
    sugar_total_g: str | None = None
    leftover_weight_g: str | None = None
    note: str | None = None
    anomaly_flags: list[AnomalyRead]
    dishes: list[LoggedDish]
    #: 当天菜单是否已经确认过（没有菜单就没法算营养）
    menu_confirmed: bool
    warning: str | None = Field(default=None, description="提示语，例如当天没有可勾选的菜品")


class LoggedDishWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dish_id: UUID
    servings_produced: Decimal = Field(ge=0)
    leftover_ratio: Decimal | None = Field(default=None, ge=0, le=1)
    leftover_weight_g: Decimal | None = Field(default=None, ge=0)
    is_substituted: bool = False
    substitution_note: str | None = Field(default=None, max_length=255)
    note: str | None = Field(default=None, max_length=255)


class DailyLogWrite(BaseModel):
    """保存一天的采集单。整份提交，缺的字段按未填处理。"""

    model_config = ConfigDict(extra="forbid")

    meal_type: MealType = MealType.LUNCH
    diner_count: int = Field(gt=0)
    oil_total_g: Decimal | None = Field(default=None, ge=0)
    salt_total_g: Decimal | None = Field(default=None, ge=0)
    sugar_total_g: Decimal | None = Field(default=None, ge=0)
    leftover_weight_g: Decimal | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=255)
    anomaly_flags: list[AnomalyFlag] = Field(default_factory=list)
    #: 当天实际供应的菜品；勾选即写入菜单日
    dishes: list[LoggedDishWrite] = Field(default_factory=list)


class DailyLogSummary(BaseModel):
    """列表页用的摘要。"""

    date: date
    meal_type: MealType
    meal_type_label: str
    diner_count: int
    oil_total_g: str | None
    salt_total_g: str | None
    sugar_total_g: str | None
    leftover_weight_g: str | None = None
    dish_count: int
    #: 出餐总重估算（份数 × 标准份量），用于算浪费率
    waste_ratio: str | None = None
    anomaly_flags: list[AnomalyRead]
    submitted_at: datetime | None = None
    submitted_by_name: str | None = None


class DailyLogPage(BaseModel):
    items: list[DailyLogSummary]
    total: int
    page: int
    page_size: int


class DailyLogSaved(BaseModel):
    """保存结果。"""

    date: date
    meal_type: MealType
    meal_type_label: str
    dish_count: int
    #: 保存后是否自动重算了当餐营养结果
    nutrition_rows: int
    submitted_at: datetime
    #: 若当天已跑过校准，这里回显校验结论
    calibration_note: str | None = None

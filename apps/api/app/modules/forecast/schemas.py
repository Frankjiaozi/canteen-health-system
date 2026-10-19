"""预测域的响应模型。"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.shared.enums import HolidayKind, MealType


class ForecastSample(BaseModel):
    """参与计算的一次历史样本。"""

    date: date
    servings: str


class DishForecast(BaseModel):
    dish_id: str
    dish_name: str
    category_label: str
    cooking_method_label: str
    predicted_servings: str
    ci_lower: str
    ci_upper: str
    #: 日历修正前的移动平均
    baseline: str
    adjustment: str
    #: SAME_WEEKDAY = 同星期几平均；OVERALL = 同星期样本不足，退化为全期平均
    basis: str
    basis_label: str
    samples: list[ForecastSample]
    #: 当日是否在菜单上
    planned: bool


class IngredientRequirement(BaseModel):
    name: str
    unit: str
    quantity: str
    unit_price: str | None = Field(default=None, description="单价，可能尚未录入")
    estimated_cost: str | None = Field(default=None, description="预计金额，缺单价时为空")


class ForecastRunResult(BaseModel):
    meal_type: MealType
    meal_type_label: str
    model_version: str
    #: 采购建议单依据哪一天的菜单推算
    basis_date: date
    #: MENU = 当天已排菜单；LAST_SAME_WEEKDAY = 上周同一天实际供应的菜
    basis: str
    basis_label: str
    dishes: list[DishForecast]
    requirements: list[IngredientRequirement]
    total_cost: str | None
    #: 日历修正的说明，例如「10 月 1 日为法定假日」
    calendar_notes: list[str]
    #: 历史样本不足以预测的菜，如实列出而不是给个凑出来的数字
    skipped: list[str]
    #: 这个字段名叫 date，会在类体里把 date 这个类型也覆盖掉，
    #: 所以声明时它必须排在其它日期类型的字段后面，否则那些注解解析不了
    date: date
    note: str


class BacktestPoint(BaseModel):
    date: date
    dish_count: int
    mape: str | None


class BacktestResult(BaseModel):
    model_version: str
    days: int
    #: 有足够历史、真的算出结果的天数。8 周数据只能回测后段，这个数字要摆出来
    usable_days: int
    #: 全期 MAPE；没有可算样本时为空
    mape: str | None
    #: 达标线：需求要求回测 MAPE 不超过 20%
    target_mape: str
    passed: bool
    points: list[BacktestPoint]
    note: str
    #: 与 ForecastRunResult 同理：date 这个字段名会覆盖类型名，必须排在日期注解之后
    start: date
    end: date


class DinerForecastSample(BaseModel):
    date: date
    diner_count: int


class DinerForecast(BaseModel):
    """某一餐的就餐人次预测。"""

    on_date: date
    meal_type: MealType
    meal_type_label: str
    predicted_diner_count: int | None = Field(
        default=None, description="预测人次；历史不足且无兜底时为空"
    )
    lower: int | None = Field(default=None, description="参考区间下界")
    upper: int | None = Field(default=None, description="参考区间上界")
    basis: str
    basis_label: str
    samples: list[DinerForecastSample]
    calendar_note: str | None = None
    note: str


class HolidayRead(BaseModel):
    id: str
    date: date
    name: str
    kind: HolidayKind
    kind_label: str
    is_verified: bool
    source_note: str | None = None


class HolidayPage(BaseModel):
    year: int
    items: list[HolidayRead]
    unverified_count: int
    note: str


class HolidayWrite(BaseModel):
    """核对入口：确认日期无误，或改掉名称与类型。"""

    name: str | None = Field(default=None, max_length=32)
    kind: HolidayKind | None = None
    is_verified: bool | None = None
    source_note: str | None = Field(default=None, max_length=255)

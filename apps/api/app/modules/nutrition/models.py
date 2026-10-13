"""营养计算结果、校准系数与膳食指南基准模型。

本模块最容易出错的地方是**口径混用**，因此用两个互相独立的维度来标记每个数值：

- `caliber`：这份数值说的是「单份」还是「人均」
- `value_type`：这份数值是配方推算、当日校准还是抽样实测

单份营养服务公开大屏与菜品查询；人均摄入服务看板与政策对标。两者混用会得出完全错误的结论。
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.mixins import NutrientColumnsMixin, SoftDeleteMixin
from app.db.types import enum_check, enum_type
from app.shared.enums import (
    CalibrationSource,
    CookingMethod,
    MealType,
    NutrientCaliber,
    NutrientCode,
    NutritionValueType,
    StandardCode,
    StandardPeriod,
)


class DishNutrition(UUIDPrimaryKeyMixin, TimestampMixin, NutrientColumnsMixin, Base):
    """菜品营养结果。

    `PER_SERVING` 是一份菜的营养；`PER_CAPITA` 是这道菜分摊到每位就餐者的摄入量
    （当日该菜实际被吃掉的营养 ÷ 就餐人次），把当日全部菜品的该口径相加即为当日人均摄入。
    """

    __tablename__ = "dish_nutritions"

    dish_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dishes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    meal_type: Mapped[MealType] = mapped_column(enum_type(MealType), nullable=False)

    caliber: Mapped[NutrientCaliber] = mapped_column(enum_type(NutrientCaliber), nullable=False)
    value_type: Mapped[NutritionValueType] = mapped_column(
        enum_type(NutritionValueType), nullable=False
    )

    # 每项营养素的误差区间，例如 {"energy_kcal": {"lower": 480.0, "upper": 660.0}}
    uncertainty: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    # 可追溯快照：所用配方、食材成分来源、校准系数、公式版本、缺失数据项
    computation_trace: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    source_note: Mapped[str | None] = mapped_column(String(255))

    __table_args__ = (
        UniqueConstraint("dish_id", "date", "meal_type", "caliber", "value_type"),
        enum_check("meal_type", MealType),
        enum_check("caliber", NutrientCaliber),
        enum_check("value_type", NutritionValueType),
        CheckConstraint("energy_kcal >= 0", name="energy_non_negative"),
        CheckConstraint(
            "protein_g >= 0 AND fat_g >= 0 AND carb_g >= 0", name="macros_non_negative"
        ),
        CheckConstraint("sodium_mg >= 0", name="sodium_non_negative"),
    )

    def __repr__(self) -> str:
        return f"<DishNutrition dish={self.dish_id} {self.caliber}/{self.value_type}>"


class CalibrationFactor(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """校准系数。

    第二层（当日闭环）按烹饪方式分组缩放；第三层（抽样纠偏）修正单道菜或
    某类烹饪方式的长期漂移。本次只建表，两层算法在后续模块实现。
    """

    __tablename__ = "calibration_factors"

    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    meal_type: Mapped[MealType] = mapped_column(enum_type(MealType), nullable=False)
    cooking_method: Mapped[CookingMethod] = mapped_column(enum_type(CookingMethod), nullable=False)
    coefficient: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    source: Mapped[CalibrationSource] = mapped_column(enum_type(CalibrationSource), nullable=False)
    basis_note: Mapped[str | None] = mapped_column(String(255))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    __table_args__ = (
        UniqueConstraint("date", "meal_type", "cooking_method", "source"),
        enum_check("meal_type", MealType),
        enum_check("cooking_method", CookingMethod),
        enum_check("source", CalibrationSource),
        CheckConstraint("coefficient > 0", name="coefficient_positive"),
    )


class NutritionStandard(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """膳食指南的量化基准，配置化存储。

    做成表而不是硬编码常量，是为了满足两条要求：数值可追溯来源、文案统一引用原文；
    同时便于后续补充《学生餐营养指南》的分年龄段区间而不必改代码。
    `target_min` / `target_max` 同为空的区间表示只考核上限（例如食盐不超过 5 克）。
    """

    __tablename__ = "nutrition_standards"

    code: Mapped[StandardCode] = mapped_column(enum_type(StandardCode), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    # 与计算结果可直接对照时的营养素代码；食用油、添加糖等对照项留空
    nutrient: Mapped[NutrientCode | None] = mapped_column(enum_type(NutrientCode))
    period: Mapped[StandardPeriod] = mapped_column(
        enum_type(StandardPeriod), nullable=False, server_default=StandardPeriod.DAILY.value
    )
    target_min: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    target_max: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))

    source: Mapped[str] = mapped_column(String(128), nullable=False)
    source_version: Mapped[str | None] = mapped_column(String(32))
    source_quote: Mapped[str | None] = mapped_column(String(255))
    note: Mapped[str | None] = mapped_column(String(255))

    __table_args__ = (
        enum_check("code", StandardCode),
        enum_check("nutrient", NutrientCode),
        enum_check("period", StandardPeriod),
        CheckConstraint(
            "target_min IS NOT NULL OR target_max IS NOT NULL",
            name="target_range_present",
        ),
        CheckConstraint(
            "target_min IS NULL OR target_max IS NULL OR target_min <= target_max",
            name="target_range_ordered",
        ),
    )

    def __repr__(self) -> str:
        return f"<NutritionStandard {self.code}>"

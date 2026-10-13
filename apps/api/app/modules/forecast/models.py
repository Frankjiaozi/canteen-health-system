"""预测结果模型。

保留 `model_version`，是因为验收标准要求「对过去两周的历史数据回测」：
不同版本模型的预测必须能分别留存、分别评估 MAPE。
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
from app.db.types import enum_check, enum_type
from app.shared.enums import MealType


class Forecast(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """某天某一餐某道菜的份数预测。"""

    __tablename__ = "forecasts"

    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    meal_type: Mapped[MealType] = mapped_column(enum_type(MealType), nullable=False)
    dish_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dishes.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    predicted_servings: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    ci_lower: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    ci_upper: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))

    model_version: Mapped[str] = mapped_column(String(32), nullable=False)
    # 输入特征快照：同星期历史、校历事件、天气、季节等，用于事后解释与复盘
    features: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    __table_args__ = (
        UniqueConstraint("date", "meal_type", "dish_id", "model_version"),
        enum_check("meal_type", MealType),
        CheckConstraint("predicted_servings >= 0", name="predicted_non_negative"),
        CheckConstraint(
            "ci_lower IS NULL OR ci_upper IS NULL OR ci_lower <= ci_upper",
            name="ci_ordered",
        ),
    )

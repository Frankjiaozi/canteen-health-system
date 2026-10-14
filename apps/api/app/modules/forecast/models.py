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
    Boolean,
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
from app.shared.enums import HolidayKind, MealType


class Holiday(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """法定节假日日历。

    预测的修正依据只有一条：**放假当天下调、调休上班的周末按工作日算**。
    之所以做成表而不是写死常量，是因为调休年年不同、且必须以国务院办公厅通知为准，
    所以还要能被核对与修正——`is_verified` 就是为此存在，界面上会把未核对的条目标出来。
    """

    __tablename__ = "holidays"

    date: Mapped[date] = mapped_column(Date, nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(32), nullable=False)
    kind: Mapped[HolidayKind] = mapped_column(enum_type(HolidayKind), nullable=False)

    #: 是否已对照国务院办公厅通知核对过。内置的 2026 年日历全部是「待核对」
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    source_note: Mapped[str | None] = mapped_column(String(255))

    __table_args__ = (enum_check("kind", HolidayKind),)

    def __repr__(self) -> str:
        return f"<Holiday {self.date} {self.name}>"


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

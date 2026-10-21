"""菜单日模型。

按 (日期, 餐次) 唯一，使离线录入重放天然幂等。
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import enum_check, enum_type
from app.shared.enums import MealType, PackageCode


class MenuDay(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """某天某一餐的菜单。"""

    __tablename__ = "menu_days"

    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    meal_type: Mapped[MealType] = mapped_column(enum_type(MealType), nullable=False)
    # 所属菜单轮换名，便于按轮换整体复制菜单
    rotation_name: Mapped[str | None] = mapped_column(String(64))
    note: Mapped[str | None] = mapped_column(String(255))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    __table_args__ = (
        UniqueConstraint("date", "meal_type"),
        enum_check("meal_type", MealType),
    )

    def __repr__(self) -> str:
        return f"<MenuDay {self.date} {self.meal_type}>"


class MenuDayItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """菜单日里的一道菜。"""

    __tablename__ = "menu_day_items"

    menu_day_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("menu_days.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dish_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dishes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    planned_servings: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    # 临时替换标记：食堂实际供应与计划不一致时置真，避免污染预测的历史序列
    is_substituted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    substitution_note: Mapped[str | None] = mapped_column(String(255))
    #: A/B 套餐归属。共用主食写 COMMON，避免采购聚合时重复计数。
    package_code: Mapped[PackageCode] = mapped_column(
        enum_type(PackageCode),
        nullable=False,
        server_default=PackageCode.COMMON.value,
    )

    __table_args__ = (
        UniqueConstraint("menu_day_id", "dish_id"),
        enum_check("package_code", PackageCode),
    )

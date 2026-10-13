"""菜单推荐模型。

可解释性是硬要求：每条推荐都必须能说明原因（例如「连续三天未供应深色蔬菜」）。
推荐只作为建议，最终由管理员确认，否决原因记录在案用于迭代。
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import enum_check, enum_type
from app.shared.enums import MealType, SuggestionStatus


class MenuSuggestion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """一次菜单推荐结果。

    不设 (日期, 餐次) 唯一约束：同一天可以保留多版推荐供对比，
    最终采纳哪一版由 `status` 表达。
    """

    __tablename__ = "menu_suggestions"

    date: Mapped[date] = mapped_column(Date, nullable=False)
    meal_type: Mapped[MealType] = mapped_column(enum_type(MealType), nullable=False)
    status: Mapped[SuggestionStatus] = mapped_column(
        enum_type(SuggestionStatus), nullable=False, server_default=SuggestionStatus.PENDING.value
    )

    # 候选菜单（菜品 + 建议份量）
    candidate_menu: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    # 与营养目标的差距说明
    nutrition_gap: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    cost_estimate: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    # 每条推荐的理由，界面上逐条展示
    reasons: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )

    rejected_reason: Mapped[str | None] = mapped_column(String(255))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_menu_suggestions_date_meal", "date", "meal_type"),
        enum_check("meal_type", MealType),
        enum_check("status", SuggestionStatus),
    )

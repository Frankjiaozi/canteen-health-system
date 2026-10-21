"""每日采集模型。

采集设计遵循一个原则：一次性建库的成本可以高，每天录入的成本必须极低。
每天只填几个数字——份数、人次、油盐糖总量、剩餐量——其余全靠配方库推导。

按 (日期, 餐次) 唯一，使离线录入的数据在联网重放时天然幂等。
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import enum_check, enum_type
from app.shared.enums import FeedbackSource, MealType, PackageCode


class DailyLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """每日记录主表：一天一餐一条。"""

    __tablename__ = "daily_logs"

    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    meal_type: Mapped[MealType] = mapped_column(enum_type(MealType), nullable=False)

    diner_count: Mapped[int] = mapped_column(Integer, nullable=False)

    # 当日油盐糖实际总用量。NULL 表示没有测量，0 表示明确测到零投放。
    oil_total_g: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    salt_total_g: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    sugar_total_g: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))

    # 当日剩餐总重（克）
    leftover_weight_g: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))

    # 异常标记，例如 ["RECEPTION", "SUSPENDED", "EQUIPMENT_FAILURE"]：
    # 这些日子的数据不应进入预测的历史序列，避免污染模型
    anomaly_flags: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    note: Mapped[str | None] = mapped_column(String(255))

    submitted_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("date", "meal_type"),
        enum_check("meal_type", MealType),
        CheckConstraint("diner_count > 0", name="diner_count_positive"),
        CheckConstraint(
            "(oil_total_g IS NULL OR oil_total_g >= 0) "
            "AND (salt_total_g IS NULL OR salt_total_g >= 0) "
            "AND (sugar_total_g IS NULL OR sugar_total_g >= 0)",
            name="seasoning_totals_non_negative",
        ),
    )

    def __repr__(self) -> str:
        return f"<DailyLog {self.date} {self.meal_type}>"


class DailyLogItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """每日记录的出品明细：一道菜的份数与剩餐。"""

    __tablename__ = "daily_log_items"

    daily_log_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("daily_logs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dish_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dishes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    servings_produced: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    # 这道菜在采集发生时使用的配方快照。历史校准不能再拿今天的配方回算过去。
    recipe_snapshot: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    # 剩余比例（0~1）。同时服务两个目标：修正实际摄入量、支撑反浪费统计
    leftover_ratio: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    leftover_weight_g: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    note: Mapped[str | None] = mapped_column(String(255))
    #: 与菜单计划保持同一套餐归属；共用主食为 COMMON。
    package_code: Mapped[PackageCode] = mapped_column(
        enum_type(PackageCode),
        nullable=False,
        server_default=PackageCode.COMMON.value,
    )

    __table_args__ = (
        UniqueConstraint("daily_log_id", "dish_id"),
        enum_check("package_code", PackageCode),
        CheckConstraint("servings_produced >= 0", name="servings_non_negative"),
        CheckConstraint(
            "leftover_ratio IS NULL OR (leftover_ratio >= 0 AND leftover_ratio <= 1)",
            name="leftover_ratio_in_range",
        ),
    )


class Feedback(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """剩餐与评分反馈。

    系统内没有学生端，因此反馈由录入员在每日采集时一并录入（`source=RECORDER`）；
    保留 `source` 字段以便后续接入其它反馈渠道而不用改表。
    """

    __tablename__ = "feedbacks"

    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    dish_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dishes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    leftover_ratio: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    rating: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[FeedbackSource] = mapped_column(
        enum_type(FeedbackSource), nullable=False, server_default=FeedbackSource.RECORDER.value
    )
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    note: Mapped[str | None] = mapped_column(String(255))

    __table_args__ = (
        enum_check("source", FeedbackSource),
        CheckConstraint("rating IS NULL OR (rating >= 1 AND rating <= 5)", name="rating_in_range"),
        CheckConstraint(
            "leftover_ratio IS NULL OR (leftover_ratio >= 0 AND leftover_ratio <= 1)",
            name="leftover_ratio_in_range",
        ),
    )

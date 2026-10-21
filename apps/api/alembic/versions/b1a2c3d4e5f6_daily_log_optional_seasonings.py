"""每日投料允许缺失，人次必须为正

油、盐、糖的 NULL 表示“没有测量”，0 表示“明确测到零投放”。把两者混成同一个值
会让未测量的餐次看起来像低盐低油，并污染后续校准。

Revision ID: b1a2c3d4e5f6
Revises: a8e2144f17aa
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b1a2c3d4e5f6"
down_revision: str | None = "a8e2144f17aa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for column in ("oil_total_g", "salt_total_g", "sugar_total_g"):
        op.alter_column(
            "daily_logs",
            column,
            existing_type=sa.Numeric(10, 2),
            nullable=True,
            server_default=None,
        )

    op.drop_constraint("diner_count_non_negative", "daily_logs", type_="check")
    op.create_check_constraint("diner_count_positive", "daily_logs", "diner_count > 0")

    op.drop_constraint("seasoning_totals_non_negative", "daily_logs", type_="check")
    op.create_check_constraint(
        "seasoning_totals_non_negative",
        "daily_logs",
        "(oil_total_g IS NULL OR oil_total_g >= 0) "
        "AND (salt_total_g IS NULL OR salt_total_g >= 0) "
        "AND (sugar_total_g IS NULL OR sugar_total_g >= 0)",
    )


def downgrade() -> None:
    # 回滚到旧的 NOT NULL 结构时，NULL 只能落成 0；这一步会丢失“未测量”语义。
    op.execute(
        "UPDATE daily_logs SET "
        "oil_total_g = COALESCE(oil_total_g, 0), "
        "salt_total_g = COALESCE(salt_total_g, 0), "
        "sugar_total_g = COALESCE(sugar_total_g, 0)"
    )
    for column in ("oil_total_g", "salt_total_g", "sugar_total_g"):
        op.alter_column(
            "daily_logs",
            column,
            existing_type=sa.Numeric(10, 2),
            nullable=False,
            server_default=sa.text("0"),
        )

    op.drop_constraint("diner_count_positive", "daily_logs", type_="check")
    op.create_check_constraint("diner_count_non_negative", "daily_logs", "diner_count >= 0")

    op.drop_constraint("seasoning_totals_non_negative", "daily_logs", type_="check")
    op.create_check_constraint(
        "seasoning_totals_non_negative",
        "daily_logs",
        "oil_total_g >= 0 AND salt_total_g >= 0 AND sugar_total_g >= 0",
    )

"""菜品补「早餐固定供应」标记

Revision ID: 992a67635cdf
Revises: 368c7b477607
Create Date: 2026-10-15 22:42:28.115101+08:00

早餐不走推荐求解——学校早餐是每天固定那几样。开了这个标记的菜构成每天的早餐，
并且不再进入午晚餐的候选池，免得同一道菜一天出现两次。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "992a67635cdf"
down_revision: str | None = "368c7b477607"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "dishes",
        sa.Column(
            "is_breakfast_staple",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("dishes", "is_breakfast_staple")

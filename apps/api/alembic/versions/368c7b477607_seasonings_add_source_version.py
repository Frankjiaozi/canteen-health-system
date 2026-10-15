"""调味料补 source_version 列

Revision ID: 368c7b477607
Revises: 77af5ca842cc
Create Date: 2026-10-15 21:24:45.953199+08:00

食材库早就有 data_source + source_version 两列，调味料只落了前者。
营养数据要「点开能看到来源与版本」这条要求对两者是一样的，补上这列，
调味料也能记下平台条目名与条目 ID。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "368c7b477607"
down_revision: str | None = "77af5ca842cc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "seasonings", sa.Column("source_version", sa.String(length=64), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("seasonings", "source_version")

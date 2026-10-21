"""菜单与采集明细增加 A/B/共用套餐标识。

Revision ID: d4e5f6a7b8c9
Revises: c2d3e4f5a6b7
Create Date: 2026-10-21 00:00:00.000000+08:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: str | Sequence[str] | None = "c2d3e4f5a6b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """旧数据按单套餐语义记录为 COMMON，可原样展示与回滚。"""
    for table in ("menu_day_items", "daily_log_items"):
        op.add_column(
            table,
            sa.Column(
                "package_code",
                sa.String(length=32),
                nullable=False,
                server_default="COMMON",
            ),
        )
        op.create_check_constraint(
            op.f(f"ck_{table}_package_code_valid"),
            table,
            "package_code IN ('A', 'B', 'COMMON')",
        )


def downgrade() -> None:
    for table in ("daily_log_items", "menu_day_items"):
        op.drop_constraint(
            op.f(f"ck_{table}_package_code_valid"),
            table,
            type_="check",
        )
        op.drop_column(table, "package_code")

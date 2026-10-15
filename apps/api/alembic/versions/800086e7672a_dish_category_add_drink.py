"""菜品类别加「饮品」

Revision ID: 800086e7672a
Revises: 992a67635cdf
Create Date: 2026-10-15 22:45:43.287754+08:00

早餐要上牛奶、豆浆这类饮品，原来的类别里没有对应的桶：塞进「汤」或「半荤」
都会让菜单结构与类别配额跟着错。加一个取值。

**CHECK 约束必须显式重建**：autogenerate 不比对 CHECK，只改 Python 枚举的话
数据库层会继续拒收新取值——那种错只在写入时才暴露。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "800086e7672a"
down_revision: str | None = "992a67635cdf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # op.f() 用来跳过 naming_convention：不给它包一层的话，名字会被再拼一次
    # 前缀，变成 ck_dishes_ck_dishes_category_valid 这种不存在的约束
    op.drop_constraint(op.f("ck_dishes_category_valid"), "dishes", type_="check")
    op.create_check_constraint(
        op.f("ck_dishes_category_valid"),
        "dishes",
        "category IN ('MEAT', 'VEGETABLE', 'HALF_MEAT', 'SOUP', 'STAPLE', 'DRINK')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_dishes_category_valid"), "dishes", type_="check")
    op.create_check_constraint(
        op.f("ck_dishes_category_valid"),
        "dishes",
        "category IN ('MEAT', 'VEGETABLE', 'HALF_MEAT', 'SOUP', 'STAPLE')",
    )

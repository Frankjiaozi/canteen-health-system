"""采集明细冻结配方快照

历史校准不能再拿当前配方回算过去。每条采集明细保存当时的配方版本、烹饪方式和
调味料分摊量；迁移前的旧行以迁移时的当前配方回填为基线。

Revision ID: c2d3e4f5a6b7
Revises: b1a2c3d4e5f6
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c2d3e4f5a6b7"
down_revision: str | None = "b1a2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "daily_log_items",
        sa.Column("recipe_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    # 旧数据没有历史版本信息，以迁移时的当前配方作为基线回填；之后再改配方
    # 不会改动这些快照。
    op.execute(
        """
        UPDATE daily_log_items AS dli
        SET recipe_snapshot = jsonb_build_object(
            'recipe_version', d.recipe_version,
            'cooking_method', d.cooking_method,
            'ingredients', COALESCE((
                SELECT jsonb_agg(jsonb_build_object(
                    'ingredient_id', ri.ingredient_id::text,
                    'quantity_per_serving_g', ri.quantity_per_serving_g::text,
                    'edible_ratio_override',
                        CASE WHEN ri.edible_ratio_override IS NULL
                             THEN NULL ELSE ri.edible_ratio_override::text END
                ))
                FROM recipe_items AS ri
                WHERE ri.dish_id = d.id
            ), '[]'::jsonb),
            'seasonings', COALESCE((
                SELECT jsonb_agg(jsonb_build_object(
                    'seasoning_id', rs.seasoning_id::text,
                    'category', s.category,
                    'quantity_per_serving_g', rs.quantity_per_serving_g::text
                ))
                FROM recipe_seasonings AS rs
                JOIN seasonings AS s ON s.id = rs.seasoning_id
                WHERE rs.dish_id = d.id
            ), '[]'::jsonb)
        )
        FROM dishes AS d
        WHERE d.id = dli.dish_id
        """
    )


def downgrade() -> None:
    op.drop_column("daily_log_items", "recipe_snapshot")

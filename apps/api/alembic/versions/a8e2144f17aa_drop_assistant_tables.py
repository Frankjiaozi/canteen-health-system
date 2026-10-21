"""移除业务侧 AI 助手的三张表

业务侧的「AI 助手」整套下线，只保留独立的「知味膳食助手」（`apps/agent`）。
它的代码、路由、配置与前端入口都已删除，这里把留在库里的三张表一并清掉。

**这会丢掉已有的对话、消息与方案记录**——这些是初始化样本数据，不是业务台账：
每一笔由助手提议、人工确认的**业务改动**仍然记在 `audit_logs` 里，
`note` 写着「经 AI 助手提议、由本人确认」，谁在什么时候改了什么依然可查。

撤回能力没有随之下线：它已经搬到 `POST /api/v1/menu-plan/{id}/undo`，
由知味膳食助手的结果面板调用（见提交 feat(menuplan): 撤回发布的入口从助手搬到接口）。

downgrade 会把三张表**按原样重建**（空表）：结构可回滚，数据不可。

Revision ID: a8e2144f17aa
Revises: 800086e7672a
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a8e2144f17aa"
down_revision: str | None = "800086e7672a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 先删子表再删父表；索引与约束随表一起消失，不必单独 drop_index
    op.drop_table("assistant_proposals")
    op.drop_table("assistant_messages")
    op.drop_table("assistant_conversations")


def downgrade() -> None:
    op.create_table(
        "assistant_conversations",
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("user_name", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(length=64), nullable=False),
        sa.Column("message_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "last_message_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_assistant_conversations_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assistant_conversations")),
    )
    op.create_index(
        op.f("ix_assistant_conversations_user_id"),
        "assistant_conversations",
        ["user_id"],
        unique=False,
    )
    op.create_table(
        "assistant_messages",
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_calls", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("truncated", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('USER', 'ASSISTANT')", name=op.f("ck_assistant_messages_role_valid")
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["assistant_conversations.id"],
            name=op.f("fk_assistant_messages_conversation_id_assistant_conversations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assistant_messages")),
        sa.UniqueConstraint(
            "conversation_id",
            "sequence",
            name=op.f("uq_assistant_messages_conversation_id_sequence"),
        ),
    )
    op.create_index(
        "ix_assistant_messages_conversation_created",
        "assistant_messages",
        ["conversation_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_assistant_messages_conversation_id"),
        "assistant_messages",
        ["conversation_id"],
        unique=False,
    )
    op.create_table(
        "assistant_proposals",
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("tool_name", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("summary", sa.String(length=512), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("preview", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="PENDING", nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("created_by_name", sa.String(length=64), nullable=True),
        sa.Column("decided_by", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.String(length=512), nullable=True),
        sa.Column("undo", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("revoked_by", sa.UUID(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'CONFIRMED', 'CANCELLED', 'FAILED', 'REVERTED')",
            name=op.f("ck_assistant_proposals_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["assistant_conversations.id"],
            name=op.f("fk_assistant_proposals_conversation_id_assistant_conversations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_assistant_proposals_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"],
            ["users.id"],
            name=op.f("fk_assistant_proposals_decided_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by"],
            ["users.id"],
            name=op.f("fk_assistant_proposals_revoked_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assistant_proposals")),
    )
    op.create_index(
        op.f("ix_assistant_proposals_conversation_id"),
        "assistant_proposals",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_assistant_proposals_status"), "assistant_proposals", ["status"], unique=False
    )

"""助手的三张表：会话、消息、待确认方案。

会话与消息落库是为了**审计**：需求要求 Agent 的操作留痕，而「谁在哪个对话里
让助手做了什么」只有把对话本身存下来才答得出来。

待确认方案（proposal）是写操作的闸门：助手不许直接写库，它先把「打算写什么」
落成一条 PENDING 的方案，用户点了确认才执行。方案本身也是留痕的一部分——
哪一版参数、谁确认的、什么时候确认的，事后都查得到。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import enum_check, enum_type
from app.shared.enums import AssistantMessageRole, AssistantProposalStatus


class AssistantConversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """一次对话。标题取第一句提问，便于在列表里认出是哪件活。"""

    __tablename__ = "assistant_conversations"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    #: 冗余保存姓名：账号停用后历史对话仍要能看懂是谁问的（与 audit_logs 同一个理由）
    user_name: Mapped[str | None] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(64), nullable=False)
    message_count: Mapped[int] = mapped_column(nullable=False, server_default="0")
    last_message_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    messages: Mapped[list[AssistantMessage]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class AssistantMessage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """对话里的一条消息。工具调用挂在助手消息上，不单独成行。"""

    __tablename__ = "assistant_messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assistant_conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[AssistantMessageRole] = mapped_column(
        enum_type(AssistantMessageRole), nullable=False
    )
    #: 会话内序号。**不能靠 created_at 排序**：同一次提问的用户消息与助手回复
    #: 在同一个事务里写入，时间戳一模一样，再按 UUID 排就是随机的——对话会前后颠倒。
    sequence: Mapped[int] = mapped_column(nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    #: 助手这一轮调了哪些工具、结果如何（便于复核答案是从哪来的）
    tool_calls: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    #: 到轮次上限还没查完时置真
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    model: Mapped[str | None] = mapped_column(String(64))

    conversation: Mapped[AssistantConversation] = relationship(back_populates="messages")

    __table_args__ = (
        Index("ix_assistant_messages_conversation_created", "conversation_id", "created_at"),
        UniqueConstraint("conversation_id", "sequence"),
        enum_check("role", AssistantMessageRole),
    )


class AssistantProposal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """待确认的写操作方案。

    `payload` 是原样存下来的工具参数，`preview` 是给人看的那份（字段、将产生的变化、
    以及问题提示）。确认时执行的是 `payload`——两者分开，是为了「页面上看到的」
    与「实际执行的」能对上，而不是各拼一份。
    """

    __tablename__ = "assistant_proposals"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assistant_conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    summary: Mapped[str] = mapped_column(String(512), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    preview: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[AssistantProposalStatus] = mapped_column(
        enum_type(AssistantProposalStatus),
        nullable=False,
        server_default=AssistantProposalStatus.PENDING.value,
        index=True,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_by_name: Mapped[str | None] = mapped_column(String(64))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: 执行结果（新建出来的实体 id 与关键字段），失败时是错误原因
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(String(512))

    __table_args__ = (enum_check("status", AssistantProposalStatus),)

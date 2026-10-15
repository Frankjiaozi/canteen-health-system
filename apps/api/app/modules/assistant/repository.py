"""助手的数据访问：会话、消息、待确认方案。"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.assistant.models import (
    AssistantConversation,
    AssistantMessage,
    AssistantProposal,
)
from app.shared.enums import AssistantProposalStatus


def create_conversation(
    session: Session, *, user_id: UUID | None, user_name: str | None, title: str, now: datetime
) -> AssistantConversation:
    conversation = AssistantConversation(
        user_id=user_id, user_name=user_name, title=title[:64], last_message_at=now
    )
    session.add(conversation)
    session.flush()
    return conversation


def get_conversation(session: Session, conversation_id: UUID) -> AssistantConversation | None:
    return session.get(AssistantConversation, conversation_id)


def list_conversations(
    session: Session, *, user_id: UUID | None = None, limit: int = 20
) -> list[AssistantConversation]:
    statement = select(AssistantConversation)
    if user_id is not None:
        statement = statement.where(AssistantConversation.user_id == user_id)
    return list(
        session.scalars(
            statement.order_by(AssistantConversation.last_message_at.desc()).limit(limit)
        ).all()
    )


def add_message(
    session: Session,
    *,
    conversation: AssistantConversation,
    role: str,
    content: str,
    tool_calls: list[dict[str, object]] | None = None,
    truncated: bool = False,
    model: str | None = None,
    now: datetime,
) -> AssistantMessage:
    """追加一条消息。序号与计数在这里一起推进，保证「第几条」永远连续、不乱序。"""
    conversation.message_count += 1
    conversation.last_message_at = now
    message = AssistantMessage(
        conversation_id=conversation.id,
        sequence=conversation.message_count,
        role=role,
        content=content,
        tool_calls=tool_calls,
        truncated=truncated,
        model=model,
    )
    session.add(message)
    session.flush()
    return message


def list_messages(
    session: Session, *, conversation_id: UUID, limit: int | None = None
) -> list[AssistantMessage]:
    statement = (
        select(AssistantMessage)
        .where(AssistantMessage.conversation_id == conversation_id)
        .order_by(AssistantMessage.sequence)
    )
    rows = list(session.scalars(statement).all())
    return rows[-limit:] if limit else rows


def create_proposal(
    session: Session,
    *,
    conversation_id: UUID,
    tool_name: str,
    title: str,
    summary: str,
    payload: dict[str, object],
    preview: dict[str, object],
    created_by: UUID | None,
    created_by_name: str | None,
) -> AssistantProposal:
    proposal = AssistantProposal(
        conversation_id=conversation_id,
        tool_name=tool_name,
        title=title[:128],
        summary=summary[:512],
        payload=payload,
        preview=preview,
        created_by=created_by,
        created_by_name=created_by_name,
    )
    session.add(proposal)
    session.flush()
    return proposal


def get_proposal(session: Session, proposal_id: UUID) -> AssistantProposal | None:
    return session.get(AssistantProposal, proposal_id)


def list_proposals(session: Session, *, conversation_id: UUID) -> list[AssistantProposal]:
    return list(
        session.scalars(
            select(AssistantProposal)
            .where(AssistantProposal.conversation_id == conversation_id)
            .order_by(AssistantProposal.created_at)
        ).all()
    )


def count_pending_proposals(session: Session) -> int:
    """全局待确认方案数。界面上的「有几件事等你确认」用它。"""
    return int(
        session.scalar(
            select(func.count())
            .select_from(AssistantProposal)
            .where(AssistantProposal.status == AssistantProposalStatus.PENDING)
        )
        or 0
    )

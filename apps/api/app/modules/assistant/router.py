"""AI 助手接口。

问一句（`/chat`）、查助手状态（`/status`）、翻历史对话（`/conversations`）、
以及方案的确认与取消（`/proposals/{id}/confirm|cancel`）。

登录即可用；写操作**不会**在 `/chat` 里落地——它只生成待确认方案，
真正的写发生在 `/proposals/{id}/confirm`，由人点一下才算数。
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_session
from app.modules.assistant import providers, service
from app.modules.assistant.schemas import (
    AssistantStatus,
    ChatReply,
    ChatRequest,
    ConversationDetail,
    ConversationSummary,
    ProposalRead,
    ToolInfo,
)
from app.modules.assistant.tools import TOOLS
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.schemas import AuthUser

router = APIRouter(prefix="/assistant", tags=["AI 助手"])


def get_chat_provider() -> providers.ChatProvider:
    """按配置给一个模型接入。测试里用 dependency_overrides 换成脚本化的假 provider。"""
    return providers.build_provider(get_settings())


def _status() -> AssistantStatus:
    settings = get_settings()
    enabled = bool(settings.assistant_base_url and settings.assistant_model)
    return AssistantStatus(
        enabled=enabled,
        model=settings.assistant_model if enabled else None,
        note=None
        if enabled
        else "还没有接模型：请配置 ASSISTANT_BASE_URL 与 ASSISTANT_MODEL（可选 ASSISTANT_API_KEY）。"
        "内网的 vLLM / Ollama 与云端 OpenAI 兼容端点都可以。",
        tools=[
            ToolInfo(name=tool.name, label=tool.label, description=tool.description)
            for tool in TOOLS
        ],
    )


@router.get("/status", response_model=AssistantStatus, summary="助手是否可用、能做什么")
def read_status(_: AuthUser = Depends(get_current_user)) -> AssistantStatus:
    return _status()


@router.get(
    "/conversations",
    response_model=list[ConversationSummary],
    summary="历史对话（审计：谁在哪个对话里让助手做了什么）",
)
def list_conversations(
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
    actor: AuthUser = Depends(get_current_user),
) -> list[ConversationSummary]:
    return service.list_conversations(session, actor=actor, limit=limit)


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationDetail,
    summary="某次对话的全部消息与方案",
)
def get_conversation(
    conversation_id: UUID,
    session: Session = Depends(get_session),
    actor: AuthUser = Depends(get_current_user),
) -> ConversationDetail:
    return service.get_conversation(session, conversation_id=conversation_id, actor=actor)


@router.post("/chat", response_model=ChatReply, summary="问助手一句话")
def chat(
    payload: ChatRequest,
    session: Session = Depends(get_session),
    actor: AuthUser = Depends(get_current_user),
    provider: providers.ChatProvider = Depends(get_chat_provider),
) -> ChatReply:
    return service.chat(session, actor=actor, payload=payload, provider=provider)


@router.post(
    "/proposals/{proposal_id}/confirm",
    response_model=ProposalRead,
    summary="确认并执行助手提出的方案",
)
def confirm_proposal(
    proposal_id: UUID,
    session: Session = Depends(get_session),
    actor: AuthUser = Depends(get_current_user),
) -> ProposalRead:
    return service.confirm_proposal(session, proposal_id=proposal_id, actor=actor)


@router.post(
    "/proposals/{proposal_id}/cancel",
    response_model=ProposalRead,
    summary="取消助手提出的方案（什么也不会发生）",
)
def cancel_proposal(
    proposal_id: UUID,
    session: Session = Depends(get_session),
    actor: AuthUser = Depends(get_current_user),
) -> ProposalRead:
    return service.cancel_proposal(session, proposal_id=proposal_id, actor=actor)

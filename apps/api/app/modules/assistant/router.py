"""AI 助手接口。

问一句（`/chat`）、查助手状态（`/status`）、翻历史对话（`/conversations`）、
以及方案的确认与取消（`/proposals/{id}/confirm|cancel`）。

登录即可用；写操作**不会**在 `/chat` 里落地——它只生成待确认方案，
真正的写发生在 `/proposals/{id}/confirm`，由人点一下才算数。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import get_session, get_session_factory
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

logger = logging.getLogger(__name__)


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


def _sse(event: dict[str, object]) -> str:
    """一条 SSE 消息。用 `data:` 单行 JSON，前端按行解析即可。"""
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


@router.post(
    "/chat/stream",
    summary="问助手一句话（流式：边查边回）",
    response_class=StreamingResponse,
)
def chat_stream(
    payload: ChatRequest,
    actor: AuthUser = Depends(get_current_user),
    provider: providers.ChatProvider = Depends(get_chat_provider),
) -> StreamingResponse:
    """流式问答。

    数据库会话在这里自己开、自己在生成器结束时关：`Depends(get_session)` 的生命周期
    是跟着请求走的，而流式响应要等生成器跑完才算结束——自己管更明确，不赌框架的时序。
    """

    def events() -> Iterator[str]:
        session = get_session_factory()()
        try:
            for event in service.chat_stream(
                session, actor=actor, payload=payload, provider=provider
            ):
                yield _sse(event)
        except AppError as error:
            session.rollback()
            yield _sse({"type": "error", "message": error.message})
        except Exception as error:
            session.rollback()
            logger.exception("助手流式对话失败：%s", error)
            yield _sse({"type": "error", "message": "助手出错了，请稍后重试"})
        finally:
            session.close()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            # 关掉缓冲：nginx 与浏览器默认会攒一段再发，那就看不到「边查边回」了
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


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

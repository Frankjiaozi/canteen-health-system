"""AI 助手接口。

两个端点：问一句（`/chat`）与查「助手能做什么」（`/status`）。
登录即可用——阶段一全是只读工具，三个角色都能问；写操作等有了确认与审计再开。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_session
from app.modules.assistant import providers, service
from app.modules.assistant.schemas import AssistantStatus, ChatReply, ChatRequest, ToolInfo
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


@router.post("/chat", response_model=ChatReply, summary="问助手一句话")
def chat(
    payload: ChatRequest,
    session: Session = Depends(get_session),
    actor: AuthUser = Depends(get_current_user),
    provider: providers.ChatProvider = Depends(get_chat_provider),
) -> ChatReply:
    return service.chat(session, actor=actor, payload=payload, provider=provider)

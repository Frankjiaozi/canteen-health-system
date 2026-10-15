"""AI 助手的请求与响应模型。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatTurn(BaseModel):
    """一轮历史对话。客户端带上最近几轮，服务端不落库（阶段一不做会话持久化）。"""

    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)


class ToolCallTrace(BaseModel):
    """助手这一轮调了哪个工具、参数是什么、结果如何。

    暴露出来有两个用处：界面上能显示「正在查食材库…」，用户也能看见答案是从哪来的——
    只给一段像模像样的话，没法核对。
    """

    name: str
    label: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    ok: bool
    summary: str
    error: str | None = None


class ChatReply(BaseModel):
    reply: str
    tool_calls: list[ToolCallTrace] = Field(default_factory=list)
    #: 来回了几轮工具调用（到上限就停，如实报出来）
    rounds: int = 0
    model: str | None = None
    #: 到轮次上限时模型还没给出结论，这句话必须让用户看见
    truncated: bool = False


class ToolInfo(BaseModel):
    """一个工具能做什么。给界面做「助手能做什么」的说明，也便于排查。"""

    name: str
    label: str
    description: str
    read_only: bool = True


class AssistantStatus(BaseModel):
    enabled: bool
    model: str | None = None
    #: 未启用时说明为什么，直接显示给用户（而不是让他对着一个点了没反应的输入框）
    note: str | None = None
    tools: list[ToolInfo] = Field(default_factory=list)

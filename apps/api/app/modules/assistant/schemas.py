"""AI 助手的请求与响应模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.shared.enums import AssistantProposalStatus


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    #: 接着哪次对话问。不填就是新开一次；历史由服务端从库里读，不信客户端传的
    conversation_id: str | None = None


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
    #: 本次对话的 id。界面上接着问要带上它，历史也从这里读
    conversation_id: str
    #: 这一轮生成的待确认方案（写操作）。界面上要渲染成确认卡片
    proposals: list[ProposalRead] = Field(default_factory=list)
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


class ProposalRead(BaseModel):
    """一份待确认的写操作方案。"""

    id: str
    conversation_id: str
    tool_name: str
    title: str
    summary: str
    #: 给人看的那份：将新增/修改哪些字段、有哪些要注意的
    preview: dict[str, Any]
    status: AssistantProposalStatus
    status_label: str
    created_by_name: str | None = None
    created_at: datetime
    decided_at: datetime | None = None
    #: 执行结果（新建出来的实体与关键字段），失败时是原因
    result: dict[str, Any] | None = None
    error: str | None = None
    #: 能不能撤回：已执行 + 留下了撤回步骤。界面据此决定给不给「撤回」按钮
    can_revoke: bool = False
    revoked_at: datetime | None = None


class ConversationSummary(BaseModel):
    id: str
    title: str
    user_name: str | None = None
    message_count: int
    pending_proposals: int = 0
    last_message_at: datetime
    created_at: datetime


class ConversationDetail(ConversationSummary):
    messages: list[ChatMessageRead]
    proposals: list[ProposalRead]


class ChatMessageRead(BaseModel):
    id: str
    role: str
    role_label: str
    content: str
    tool_calls: list[ToolCallTrace] = Field(default_factory=list)
    truncated: bool = False
    model: str | None = None
    created_at: datetime


class AssistantStatus(BaseModel):
    enabled: bool
    model: str | None = None
    #: 未启用时说明为什么，直接显示给用户（而不是让他对着一个点了没反应的输入框）
    note: str | None = None
    tools: list[ToolInfo] = Field(default_factory=list)

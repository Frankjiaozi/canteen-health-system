"""助手的一次对话：把问题交给模型，模型要用数据就调只读工具，最后回一句人话。

这一层自己不接触数据库表——它只做三件事：拼系统提示、执行模型点名的工具、把结果回给模型。
工具是**进程内**调用各业务域的 service：不绕 HTTP，权限与事务语义跟界面上操作完全一致。
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.modules.assistant import providers, tools
from app.modules.assistant.schemas import ChatReply, ChatRequest, ToolCallTrace
from app.modules.auth.schemas import AuthUser

logger = get_logger(__name__)

#: 系统提示词。写清楚三件事：你是谁、数据从哪来、不许干什么。
#: 最后一条最重要——营养值与成本一律来自工具返回，模型不许自己估，
#: 这个系统的可信度就建立在「每个数都能回溯」上。
SYSTEM_PROMPT = """你是「知味 · 校园智慧膳食平台」里的助手，服务对象是食堂录入员、食堂管理员与学校管理方。

回答要求：
1. 只依据工具返回的数据作答。**不要自己估算或编造任何营养值、单价、份数与统计数字。**
2. 工具没查到、或某项数据缺失（例如食材的某项成分为空），就如实说没有，并说明可能的原因。
3. 数字要带上口径与单位：营养按「每 100 克可食部」还是「单份」、金额是「元/公斤市品」还是估算值。
4. 涉及营养结论时说明依据（例如《中国居民膳食指南（2022）》的量化指标），不要给个体化的健康建议。
5. 用中文、简短直接，先给结论再给数据。不要罗列工具名与调用过程（界面上已经显示了）。

你目前只有**只读**工具：可以查食材、菜品配方、某天的菜单、看板指标与最近采集。
用户要求录入、修改、删除时，说明这些操作要在对应页面手动完成，你这一版还不能代做。
"""


def _system_message(actor: AuthUser) -> dict[str, Any]:
    return {
        "role": "system",
        "content": (
            f"{SYSTEM_PROMPT}\n"
            f"今天的日期是 {tools.today().isoformat()}。"
            f"当前用户是「{actor.display_name}」，角色「{actor.role_label}」。"
        ),
    }


def _tool_message(call_id: str, payload: dict[str, Any], ok: bool) -> dict[str, Any]:
    """工具结果回给模型时用 JSON 字符串：结构化的东西让它自己读，别塞成一坨中文。"""
    return {
        "role": "tool",
        "tool_call_id": call_id,
        "content": json.dumps(payload, ensure_ascii=False, default=str)[:20000]
        if ok
        else json.dumps({"error": payload.get("error")}, ensure_ascii=False),
    }


def _summarize(tool: tools.Tool, payload: dict[str, Any]) -> str:
    if "error" in payload:
        return str(payload["error"])
    if "items" in payload:
        return f"{tool.label}：返回 {len(payload['items'])} 条（共 {payload.get('total', '—')} 条）"
    if "菜品" in payload:
        return f"{tool.label}：{payload['菜品']}"
    if "汇总" in payload:
        return f"{tool.label}：统计最近 {payload.get('统计天数', '—')} 天"
    if "日期" in payload:
        return f"{tool.label}：{payload['日期']} {payload.get('餐次', '')}"
    return f"{tool.label}：已查"


def _run_tool(
    session: Session, actor: AuthUser, call: providers.ProviderToolCall
) -> tuple[dict[str, Any], ToolCallTrace]:
    tool = tools.TOOLS_BY_NAME.get(call.name)
    arguments = providers.parse_arguments(call.arguments)

    if tool is None:
        error = f"没有名为 {call.name} 的工具。可用工具：{'、'.join(tools.TOOLS_BY_NAME)}"
        payload = {"error": error}
        return payload, ToolCallTrace(
            name=call.name,
            label=call.name,
            arguments=arguments,
            ok=False,
            summary=error,
            error=error,
        )
    if actor.role not in tools.ALLOWED_ROLES:
        error = "当前角色没有使用助手的权限"
        return {"error": error}, ToolCallTrace(
            name=tool.name,
            label=tool.label,
            arguments=arguments,
            ok=False,
            summary=error,
            error=error,
        )

    try:
        payload = tool.handler(session, **arguments)
    except AppError as error:
        # 工具的业务错误要原样回给模型（「没找到这道菜」「日期格式不对」），
        # 让它据此改正或如实告诉用户，而不是抛成 500 让整轮对话断掉
        payload = {"error": str(error)}
        return payload, ToolCallTrace(
            name=tool.name,
            label=tool.label,
            arguments=arguments,
            ok=False,
            summary=str(error),
            error=str(error),
        )

    logger.info("助手调用工具：%s %s（%s）", tool.name, arguments, actor.display_name)
    return payload, ToolCallTrace(
        name=tool.name,
        label=tool.label,
        arguments=arguments,
        ok=True,
        summary=_summarize(tool, payload),
    )


def chat(
    session: Session,
    *,
    actor: AuthUser,
    payload: ChatRequest,
    provider: providers.ChatProvider,
) -> ChatReply:
    """跑一轮对话（可能来回几次工具调用），返回最终回答与用到的工具。"""
    max_rounds = get_settings().assistant_max_tool_rounds
    messages: list[dict[str, Any]] = [_system_message(actor)]
    for turn in payload.history:
        messages.append({"role": turn.role, "content": turn.content})
    messages.append({"role": "user", "content": payload.message})

    traces: list[ToolCallTrace] = []
    for round_index in range(1, max_rounds + 1):
        reply = provider.complete(messages=messages, tools=tools.tool_payload())
        if not reply.tool_calls:
            return ChatReply(
                reply=reply.text.strip() or "（模型没有给出回答）",
                tool_calls=traces,
                rounds=round_index,
                model=getattr(provider, "model", None),
            )

        messages.append(
            {
                "role": "assistant",
                "content": reply.text,
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {"name": call.name, "arguments": call.arguments},
                    }
                    for call in reply.tool_calls
                ],
            }
        )
        for call in reply.tool_calls:
            result, trace = _run_tool(session, actor, call)
            traces.append(trace)
            messages.append(_tool_message(call.id, result, trace.ok))

    logger.warning("助手到了工具调用轮次上限（%d 轮）仍未收敛", max_rounds)
    return ChatReply(
        reply=(
            "这个问题需要查的东西比较多，我查了几轮还没查完。"
            "换个更具体的问法（例如指定某一天、某道菜）我再试一次。"
        ),
        tool_calls=traces,
        rounds=max_rounds,
        model=getattr(provider, "model", None),
        truncated=True,
    )

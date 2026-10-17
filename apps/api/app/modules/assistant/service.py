"""助手的一次对话：把问题交给模型，模型要用数据就调工具，最后回一句人话。

这一层自己不接触数据库表——它只做三件事：拼系统提示、执行模型点名的工具、把结果回给模型。
工具是**进程内**调用各业务域的 service：不绕 HTTP，权限与事务语义跟界面上操作完全一致。

两处闸门都在这层：

- 会话与消息**落库**（审计要能回答「谁在哪个对话里让助手做了什么」）；
- 写工具**不执行**，只落一条待确认方案，等人点确认才走 `confirm_proposal`。
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, BusinessRuleError, ForbiddenError, NotFoundError
from app.core.logging import get_logger
from app.modules.assistant import providers, repository, tools
from app.modules.assistant.models import AssistantConversation, AssistantProposal
from app.modules.assistant.schemas import (
    ChatMessageRead,
    ChatReply,
    ChatRequest,
    ConversationDetail,
    ConversationSummary,
    ProposalRead,
    ToolCallTrace,
)
from app.modules.audit import service as audit_service
from app.modules.auth.schemas import AuthUser
from app.shared.enums import AssistantMessageRole, AssistantProposalStatus, UserRole

logger = get_logger(__name__)

#: 带上多少轮历史。多了费 token，也没必要——问的通常是眼下这件事。
HISTORY_MESSAGES = 8

#: 同一轮对话里，同一个只读接口最多连查几次。
#: 实测踩到：模型想找「哪天有抽样候选」，就一天一天地换日期扫，把轮次预算烧光，
#: 最后什么结论也没给。这个接口一次只答一格数据，扫不是办法——
#: 与其让它耗到上限，不如早点把这件事告诉它，让它去问用户想看哪天。
REPEAT_READ_LIMIT = 3

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

你可以查数据（食材、菜品配方、某天的菜单、看板指标、最近采集），也可以**提出**写操作：
新增食材、新增菜品与配方。

写操作的规矩（很重要）：
- 调用写工具**不会真的写库**，它只会生成一份待确认的方案。你必须把方案讲给用户听
  （要新增什么、关键字段是什么、有没有对不上的地方），并请他**在界面上点确认**。
- **绝不要说「已经建好了」**——没确认之前什么都没发生。没确认时你可以说「我准备好了方案，请你确认」。
- 方案里有「食材库里没有某某」这类提示时，先把这件事讲清楚，建议用户先建那条食材。
- **用户明确要「排/定某天某餐的菜单」时，要在同一轮里把确认卡片直接摆出来**：
  先 generate_menu_plan 排方案，紧接着 sync_menu_plan 生成待确认的方案，
  然后告诉用户「方案好了，确认就写进去」。不要只给方案让他再说一句「同步」——
  那一步纯属多余。反过来，用户只是随口问「明天吃什么好」时不要弹卡片，给方案就行。

录入、修改、删除超出这两个写工具的其它操作，说明要在对应页面手动完成。
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
    """工具痕迹那一行话。

    必须短：它是给人扫一眼「刚才在干什么」的，把整段 JSON 印出来就变成噪音了
    （实测：排菜单的结果整坨铺在对话里，把确认卡片顶到看不见）。
    """
    if "error" in payload:
        return str(payload["error"])
    if isinstance(payload.get("菜品"), list):
        dishes = payload["菜品"]
        purchase = payload.get("采购") or {}
        money = f"，采购 {purchase.get('项数', '—')} 项 {purchase.get('合计金额_元', '—')} 元"
        return f"{tool.label}：{len(dishes)} 道菜{money}"
    if "items" in payload:
        return f"{tool.label}：返回 {len(payload['items'])} 条（共 {payload.get('total', '—')} 条）"
    if "菜品" in payload:
        return f"{tool.label}：{payload['菜品']}"
    if "汇总" in payload:
        return f"{tool.label}：统计最近 {payload.get('统计天数', '—')} 天"
    if "日期" in payload:
        return f"{tool.label}：{payload['日期']} {payload.get('餐次', '')}"
    if "接口" in payload:
        return f"{tool.label}：{payload['接口']}"
    return f"{tool.label}：已查"


def _run_tool(
    session: Session,
    actor: AuthUser,
    call: providers.ProviderToolCall,
    *,
    conversation: AssistantConversation,
    created: list[AssistantProposal],
    traces: list[ToolCallTrace],
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

    if tool.name == "call_api":
        target = str(arguments.get("path") or "")
        repeats = sum(
            1
            for trace in traces
            if trace.name == "call_api" and str(trace.arguments.get("path")) == target
        )
        if repeats >= REPEAT_READ_LIMIT:
            error = (
                f"同一个接口（{target}）在一轮对话里已经查了 {repeats} 次。"
                "它一次只回答一个条件下的数据，换着参数扫不是办法——"
                "把已经查到的整理给用户，或者直接问他想看哪一天、哪一餐。"
            )
            return {"error": error}, ToolCallTrace(
                name=tool.name,
                label=tool.label,
                arguments=arguments,
                ok=False,
                summary=error,
                error=error,
            )

    try:
        if tool.read_only:
            if tool.handler is None:  # 由 assert_write_boundary 兜住，这里只为类型收窄
                raise BusinessRuleError(f"工具 {tool.name} 没有实现")
            # 需要身份的读工具（call_api）用当前用户的身份去查，不额外提权
            if tool.needs_actor:
                payload = tool.handler(session, actor=actor, **arguments)
            else:
                payload = tool.handler(session, **arguments)
        else:
            payload = _propose(
                session, actor, tool, arguments, conversation=conversation, created=created
            )
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


def _propose(
    session: Session,
    actor: AuthUser,
    tool: tools.Tool,
    arguments: dict[str, Any],
    *,
    conversation: AssistantConversation,
    created: list[AssistantProposal],
) -> dict[str, Any]:
    """写工具走这条路：只落一条待确认方案，一个字节的业务数据都不写。

    方案里带的 `payload` 就是确认时要执行的参数——页面上看到的与实际执行的必须是同一份，
    否则「确认」这个词就没有意义了。
    """
    assert tool.build_draft is not None  # 由 assert_write_boundary 保证
    draft = tool.build_draft(session, **arguments)
    proposal = repository.create_proposal(
        session,
        conversation_id=conversation.id,
        tool_name=tool.name,
        title=draft["title"],
        summary=draft["summary"],
        payload=draft["payload"],
        preview=draft["preview"],
        created_by=actor.id,
        created_by_name=actor.display_name,
    )
    created.append(proposal)
    logger.info("助手提出写方案：%s（%s）", proposal.title, actor.display_name)
    return {
        "状态": "待用户确认",
        "方案": proposal.summary,
        "说明": "这一步还没有写库。请把方案讲给用户听，并请他在界面上点确认。",
        "提示": draft["preview"].get("提示", []),
    }


def chat(
    session: Session,
    *,
    actor: AuthUser,
    payload: ChatRequest,
    provider: providers.ChatProvider,
) -> ChatReply:
    """跑一轮对话并返回最终结果。**实现只有一套**——它就是 `chat_stream` 的薄包装：

    非流式只是「把流抽干再返回最后一个事件」。两条路各写一遍的话，
    迟早出现「流式那版忘了落库」这类只在其中一条路上发生的 bug。
    """
    reply: ChatReply | None = None
    for event in chat_stream(session, actor=actor, payload=payload, provider=provider):
        if event["type"] == "done":
            reply = ChatReply(**event["reply"])
        elif event["type"] == "error":
            raise BusinessRuleError(str(event["message"]))
    if reply is None:
        raise BusinessRuleError("助手没有返回结果")
    return reply


def chat_stream(
    session: Session,
    *,
    actor: AuthUser,
    payload: ChatRequest,
    provider: providers.ChatProvider,
) -> Iterator[dict[str, Any]]:
    """跑一轮对话，边跑边把过程吐出来。

    事件类型：`start`（对话 id）、`tool_start`（开始查什么）、`tool`（查得怎么样）、
    `delta`（回答的一个片段）、`done`（最终结果，含待确认方案）、`error`。
    界面上「正在查食材库…」和逐字出现的回答都来自这里；`done` 之后才落库与提交。
    """
    max_rounds = get_settings().assistant_max_tool_rounds
    now = datetime.now(get_settings().timezone)
    conversation = _resolve_conversation(session, actor=actor, payload=payload, now=now)
    messages: list[dict[str, Any]] = [_system_message(actor)]
    # 历史从库里读：客户端传什么都不算数，审计与模型看到的必须是同一份
    for turn in repository.list_messages(
        session, conversation_id=conversation.id, limit=HISTORY_MESSAGES
    ):
        messages.append({"role": turn.role.lower(), "content": turn.content})
    messages.append({"role": "user", "content": payload.message})
    repository.add_message(
        session,
        conversation=conversation,
        role=AssistantMessageRole.USER.value,
        content=payload.message,
        now=now,
    )
    yield {"type": "start", "conversation_id": str(conversation.id)}

    traces: list[ToolCallTrace] = []
    proposals: list[AssistantProposal] = []
    spent = sum(
        providers.estimate_tokens(str(message.get("content") or "")) for message in messages
    )
    budget = get_settings().assistant_turn_token_budget
    for round_index in range(1, max_rounds + 1):
        reply: providers.ProviderReply | None = None
        for chunk in provider.stream(messages=messages, tools=tools.tool_payload()):
            if chunk.text:
                yield {"type": "delta", "text": chunk.text}
            if chunk.reply is not None:
                reply = chunk.reply
        if reply is None:
            raise BusinessRuleError("模型没有返回结果")
        spent += _usage_or_estimate(reply)

        if not reply.tool_calls:
            answered = _finish(
                session,
                conversation=conversation,
                text=reply.text.strip() or "（模型没有给出回答）",
                traces=traces,
                proposals=proposals,
                rounds=round_index,
                model=getattr(provider, "model", None),
                truncated=False,
                now=now,
                tokens=spent,
            )
            yield {"type": "done", "reply": answered.model_dump(mode="json")}
            return

        if spent >= budget:
            # 单次调用的输出上限管不住「来回几轮、每轮都塞一屏数据」这种花法，
            # 所以在总量上再设一道闸：到点停下来并说明，而不是悄悄烧穿预算
            logger.warning("助手单轮对话预算用完（约 %d token，上限 %d）", spent, budget)
            stopped = _finish(
                session,
                conversation=conversation,
                text=(
                    f"这一轮要查的东西太多，已经用掉约 {spent} token（上限 {budget}），先停下来。"
                    "把问题拆小一点再问——例如指定某一天、某一道菜、某一项指标。"
                ),
                traces=traces,
                proposals=proposals,
                rounds=round_index,
                model=getattr(provider, "model", None),
                truncated=True,
                now=now,
                tokens=spent,
            )
            yield {"type": "done", "reply": stopped.model_dump(mode="json")}
            return

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
            tool = tools.TOOLS_BY_NAME.get(call.name)
            yield {
                "type": "tool_start",
                "name": call.name,
                "label": tool.label if tool else call.name,
            }
            tool_result, trace = _run_tool(
                session,
                actor,
                call,
                conversation=conversation,
                created=proposals,
                traces=traces,
            )
            traces.append(trace)
            messages.append(_tool_message(call.id, tool_result, trace.ok))
            spent += providers.estimate_tokens(str(trace.summary))
            yield {"type": "tool", "trace": trace.model_dump(mode="json")}

    logger.warning("助手到了工具调用轮次上限（%d 轮）仍未收敛", max_rounds)
    final = _finish(
        session,
        conversation=conversation,
        text=(
            "这个问题需要查的东西比较多，我查了几轮还没查完。"
            "换个更具体的问法（例如指定某一天、某道菜）我再试一次。"
        ),
        traces=traces,
        proposals=proposals,
        rounds=max_rounds,
        model=getattr(provider, "model", None),
        truncated=True,
        now=now,
        tokens=spent,
    )
    yield {"type": "done", "reply": final.model_dump(mode="json")}


def _usage_or_estimate(reply: providers.ProviderReply) -> int:
    """这一轮花了多少 token：服务端给了真实用量就用它，否则按文字粗估。"""
    usage = reply.usage or {}
    total = usage.get("total_tokens")
    if isinstance(total, (int, float)):
        return int(total)
    written = providers.estimate_tokens(reply.text)
    return written + sum(
        providers.estimate_tokens(f"{call.name}{call.arguments}") for call in reply.tool_calls
    )


def _resolve_conversation(
    session: Session, *, actor: AuthUser, payload: ChatRequest, now: datetime
) -> AssistantConversation:
    """接上一次对话，或者新开一次。别人的对话不给接。"""
    if payload.conversation_id:
        try:
            conversation_id = UUID(payload.conversation_id)
        except ValueError as error:
            raise BusinessRuleError("对话 id 格式不对") from error
        conversation = repository.get_conversation(session, conversation_id)
        if conversation is None:
            raise NotFoundError("对话不存在")
        if conversation.user_id is not None and conversation.user_id != actor.id:
            raise BusinessRuleError("这是别人的对话，不能接着问")
        return conversation
    return repository.create_conversation(
        session,
        user_id=actor.id,
        user_name=actor.display_name,
        title=payload.message.strip().replace("\n", " "),
        now=now,
    )


def _readable(error: object) -> list[str]:
    """把异常整理成能显示给人看的一两句话。

    pydantic 的校验错误自带字段定位（`loc`），比 `str(异常)` 那一长串好用得多——
    用户看到的应该是「category 取值无效」，而不是「1 validation error for ...」。
    """
    errors = getattr(error, "errors", None)
    if callable(errors):
        lines = []
        for item in errors():
            field = ".".join(str(part) for part in item.get("loc", ())) or "参数"
            lines.append(f"{field}：{item.get('msg', '取值无效')}")
        if lines:
            return lines
    return [str(error)]


def _finish(
    session: Session,
    *,
    conversation: AssistantConversation,
    text: str,
    traces: list[ToolCallTrace],
    proposals: list[AssistantProposal],
    rounds: int,
    model: str | None,
    truncated: bool,
    now: datetime,
    tokens: int = 0,
) -> ChatReply:
    repository.add_message(
        session,
        conversation=conversation,
        role=AssistantMessageRole.ASSISTANT.value,
        content=text,
        tool_calls=[trace.model_dump(mode="json") for trace in traces],
        truncated=truncated,
        model=model,
        now=now,
    )
    session.commit()
    return ChatReply(
        reply=text,
        tool_calls=traces,
        conversation_id=str(conversation.id),
        proposals=[read_proposal(row) for row in proposals],
        rounds=rounds,
        model=model,
        truncated=truncated,
        tokens_used=tokens,
    )


# ---------------------------------------------------------------------------
# 方案：读、确认、取消
# ---------------------------------------------------------------------------
def read_proposal(row: AssistantProposal) -> ProposalRead:
    return ProposalRead(
        id=str(row.id),
        conversation_id=str(row.conversation_id),
        tool_name=row.tool_name,
        title=row.title,
        summary=row.summary,
        preview=row.preview,
        status=row.status,
        status_label=row.status.label,
        created_by_name=row.created_by_name,
        created_at=row.created_at,
        decided_at=row.decided_at,
        result=row.result,
        error=row.error,
        can_revoke=(
            row.status is AssistantProposalStatus.CONFIRMED
            and bool(row.undo)
            and row.revoked_at is None
        ),
        revoked_at=row.revoked_at,
    )


def _load_proposal(session: Session, proposal_id: UUID, actor: AuthUser) -> AssistantProposal:
    proposal = session.scalar(
        select(AssistantProposal)
        .where(AssistantProposal.id == proposal_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if proposal is None:
        raise NotFoundError("这条方案不存在")
    if proposal.created_by is not None and proposal.created_by != actor.id:
        raise BusinessRuleError("这是别人那条对话里的方案，请让他本人确认")
    return proposal


def confirm_proposal(session: Session, *, proposal_id: UUID, actor: AuthUser) -> ProposalRead:
    """用户点了确认，这才真正写库。

    写的是方案里存下来的那份 `payload`：页面上看到什么，执行的就是什么。
    执行走各域自己的 service，所以校验、留痕与页面录入完全一致；`audit_note` 会标明
    这条数据是「经 AI 助手提议、由本人确认」来的——留痕要能区分人和助手。
    """
    if actor.role not in {UserRole.RECORDER, UserRole.CANTEEN_ADMIN}:
        raise ForbiddenError("当前账号只能查看，不能确认写入数据")
    proposal = _load_proposal(session, proposal_id, actor)
    if proposal.status is not AssistantProposalStatus.PENDING:
        raise BusinessRuleError(f"这条方案已经{proposal.status.label}了，不能重复处理")

    tool = tools.TOOLS_BY_NAME.get(proposal.tool_name)
    if tool is None or tool.execute is None:
        raise BusinessRuleError(f"这条方案对应的操作（{proposal.tool_name}）已经不可用")

    proposal.decided_by = actor.id
    proposal.decided_at = datetime.now(get_settings().timezone)
    try:
        if tool.name in {"set_menu_day", "sync_menu_plan", "save_collection"}:
            outcome = tool.execute(session, proposal.payload, actor=actor, commit=False)
        else:
            outcome = tool.execute(session, proposal.payload, actor=actor)
    except (AppError, ValidationError) as error:
        # 执行失败也要落痕：方案留在 FAILED，原因写清楚，必要时改参数重试
        session.rollback()
        reloaded = repository.get_proposal(session, proposal_id)
        if reloaded is not None:
            reloaded.status = AssistantProposalStatus.FAILED
            # 校验错误的信息很长（pydantic 会把整条输入抄一遍），截断给界面用
            reloaded.error = "；".join(_readable(error))[:512]
            reloaded.decided_by = actor.id
            reloaded.decided_at = datetime.now(get_settings().timezone)
            session.commit()
            return read_proposal(reloaded)
        raise

    # 菜单/采集由本层统一提交业务与卡片；其他原有领域工具仍自行提交。
    reloaded = repository.get_proposal(session, proposal_id)
    if reloaded is None:
        raise NotFoundError("这条方案不存在")
    reloaded.status = AssistantProposalStatus.CONFIRMED
    reloaded.result = outcome.result
    # 撤回要做的事跟着结果一起落库：它只有在执行这一刻是准的
    reloaded.undo = (
        [{"tool": step.tool, "payload": step.payload} for step in outcome.undo]
        if outcome.undo
        else None
    )
    reloaded.error = None
    session.commit()
    logger.info("方案已确认执行：%s（%s）", reloaded.title, actor.display_name)
    return read_proposal(reloaded)


def cancel_proposal(session: Session, *, proposal_id: UUID, actor: AuthUser) -> ProposalRead:
    proposal = _load_proposal(session, proposal_id, actor)
    if proposal.status is not AssistantProposalStatus.PENDING:
        raise BusinessRuleError(f"这条方案已经{proposal.status.label}了，不能重复处理")
    proposal.status = AssistantProposalStatus.CANCELLED
    proposal.decided_by = actor.id
    proposal.decided_at = datetime.now(get_settings().timezone)
    session.commit()
    return read_proposal(proposal)


def revoke_proposal(session: Session, *, proposal_id: UUID, actor: AuthUser) -> ProposalRead:
    """撤回一条已经执行的方案：把数据改回执行之前的样子。

    这是「误操作」的出口，所以它本身也要有边界：

    - 只有**已执行**的方案能撤回（待确认的直接取消就行，什么也没发生）；
    - 执行时没给出撤回步骤的（例如将来某些不可逆的操作）如实说不能撤回；
    - **同一条数据在执行之后又被别人改过的话，拒绝撤回**——否则会把别人那一次改动一起抹掉。
      宁可让人手工核对，也不做这种「静默覆盖」。
    """
    if actor.role not in {UserRole.RECORDER, UserRole.CANTEEN_ADMIN}:
        raise ForbiddenError("当前账号只能查看，不能撤回写入数据")
    proposal = _load_proposal(session, proposal_id, actor)
    if proposal.status is AssistantProposalStatus.REVERTED:
        raise BusinessRuleError("这条方案已经撤回过了")
    if proposal.status is not AssistantProposalStatus.CONFIRMED:
        raise BusinessRuleError(f"这条方案是「{proposal.status.label}」，不能撤回")
    if not proposal.undo:
        raise BusinessRuleError("这条操作没有留下撤回步骤（不可逆），请到对应页面手工订正")

    decided_at = proposal.decided_at or proposal.updated_at
    for step in proposal.undo:
        entity_id = next(
            (value for key, value in (step.get("payload") or {}).items() if key.endswith("_id")),
            None,
        )
        if entity_id and audit_service.has_change_after(
            session, entity_id=entity_id, since=decided_at
        ):
            raise BusinessRuleError(
                "这条数据在执行之后又被改过了，撤回会连那一次改动一起抹掉；"
                "请先看清当前值，需要的话手工改回去"
            )

    for step in proposal.undo:
        tool = tools.TOOLS_BY_NAME.get(str(step.get("tool")))
        if tool is None or tool.execute is None:
            raise BusinessRuleError(f"撤回步骤「{step.get('tool')}」已经不可用")
        if tool.name in {"restore_menu_day", "restore_collection"}:
            tool.execute(session, dict(step.get("payload") or {}), actor=actor, commit=False)
        else:
            tool.execute(session, dict(step.get("payload") or {}), actor=actor)

    reloaded = repository.get_proposal(session, proposal_id)
    if reloaded is None:
        raise NotFoundError("这条方案不存在")
    reloaded.status = AssistantProposalStatus.REVERTED
    reloaded.revoked_by = actor.id
    reloaded.revoked_at = datetime.now(get_settings().timezone)
    reloaded.error = None
    session.commit()
    logger.info("方案已撤回：%s（%s）", reloaded.title, actor.display_name)
    return read_proposal(reloaded)


# ---------------------------------------------------------------------------
# 会话：列表与详情（审计用：谁在哪个对话里让助手做了什么）
# ---------------------------------------------------------------------------
def read_conversation_summary(session: Session, row: AssistantConversation) -> ConversationSummary:
    pending = sum(
        1
        for proposal in repository.list_proposals(session, conversation_id=row.id)
        if proposal.status is AssistantProposalStatus.PENDING
    )
    return ConversationSummary(
        id=str(row.id),
        title=row.title,
        user_name=row.user_name,
        message_count=row.message_count,
        pending_proposals=pending,
        last_message_at=row.last_message_at,
        created_at=row.created_at,
    )


def list_conversations(
    session: Session, *, actor: AuthUser, limit: int = 20
) -> list[ConversationSummary]:
    """列对话。默认只看自己的；食堂管理员与学校管理方可以看全部（审计视角）。"""
    scope_all = actor.role in {UserRole.CANTEEN_ADMIN, UserRole.SCHOOL_ADMIN}
    rows = repository.list_conversations(
        session, user_id=None if scope_all else actor.id, limit=limit
    )
    return [read_conversation_summary(session, row) for row in rows]


def get_conversation(
    session: Session, *, conversation_id: UUID, actor: AuthUser
) -> ConversationDetail:
    row = repository.get_conversation(session, conversation_id)
    if row is None:
        raise NotFoundError("对话不存在")
    scope_all = actor.role in {UserRole.CANTEEN_ADMIN, UserRole.SCHOOL_ADMIN}
    if not scope_all and row.user_id is not None and row.user_id != actor.id:
        raise BusinessRuleError("这是别人的对话，只有食堂管理员与学校管理方可以查阅")
    summary = read_conversation_summary(session, row)
    messages = repository.list_messages(session, conversation_id=row.id)
    return ConversationDetail(
        **summary.model_dump(),
        messages=[
            ChatMessageRead(
                id=str(message.id),
                role=message.role.value,
                role_label=message.role.label,
                content=message.content,
                tool_calls=[ToolCallTrace(**trace) for trace in (message.tool_calls or [])],
                truncated=message.truncated,
                model=message.model,
                created_at=message.created_at,
            )
            for message in messages
        ],
        proposals=[
            read_proposal(proposal)
            for proposal in repository.list_proposals(session, conversation_id=row.id)
        ],
    )

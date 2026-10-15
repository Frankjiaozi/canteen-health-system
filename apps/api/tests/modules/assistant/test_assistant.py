"""AI 助手的行为约定（阶段一：只读）。

这里**不调用真实模型**：模型是外部服务，测它等于测别人的接口。
所以用例分两层——

- **工具层**用真实数据库：查出来的必须是库里种着的食材、菜品、菜单与指标，
  这一层是「助手说的话有没有依据」的根，不能用假数据糊过去；
- **对话层**注入一个照着剧本回答的 provider：验的是我们自己的东西——
  工具调用怎么派发、业务错误怎么回给模型而不是冒成 500、轮次上限会不会兜住、
  未配置模型时是不是如实说不可用。

真实模型的连通性只能在部署环境里手动验（配置 ASSISTANT_* 之后点一次助手）。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from app.db.session import get_session_factory
from app.modules.assistant import providers, service, tools
from app.modules.assistant.router import get_chat_provider
from app.modules.assistant.schemas import ChatReply, ChatRequest, ChatTurn
from app.modules.auth.repository import get_by_username
from app.modules.auth.service import to_auth_user
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

BASE = "/api/v1/assistant"


@pytest.fixture
def db_session() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def actor(db_session: Session):
    user = get_by_username(db_session, "recorder")
    assert user is not None
    return to_auth_user(user)


class ScriptedProvider:
    """照着剧本回答的 provider：第 N 次调用返回脚本的第 N 步。"""

    name = "scripted"
    model = "scripted-model"

    def __init__(self, script: list[providers.ProviderReply]) -> None:
        self._script = list(script)
        self.calls: list[list[dict[str, Any]]] = []

    def complete(self, *, messages, tools):  # type: ignore[no-untyped-def]
        self.calls.append([dict(message) for message in messages])
        if not self._script:
            return providers.ProviderReply(text="（剧本用完了）")
        return self._script.pop(0)


def _call(name: str, arguments: str = "{}") -> providers.ProviderReply:
    return providers.ProviderReply(
        text="",
        tool_calls=[providers.ProviderToolCall(id="call-1", name=name, arguments=arguments)],
    )


@pytest.fixture
def install_provider(api_app: FastAPI) -> Iterator[Callable[[ScriptedProvider], ScriptedProvider]]:
    """把接口用的 provider 换成脚本化实现，用例结束后摘掉覆盖。"""

    def _install(provider: ScriptedProvider) -> ScriptedProvider:
        api_app.dependency_overrides[get_chat_provider] = lambda: provider
        return provider

    yield _install
    api_app.dependency_overrides.pop(get_chat_provider, None)


# ---------------------------------------------------------------------------
# 只读这条线：工具集里不许有写操作
# ---------------------------------------------------------------------------
def test_tools_are_all_read_only() -> None:
    """阶段一的分界线：工具一旦能写，就必须先有确认与审计。"""
    tools.assert_read_only()
    assert len(tools.TOOLS) >= 5
    assert all(tool.read_only for tool in tools.TOOLS)


# ---------------------------------------------------------------------------
# 工具层：数据必须来自真实库
# ---------------------------------------------------------------------------
def test_search_ingredients_returns_seeded_data(db_session: Session) -> None:
    # 库里叫「马铃薯」（菜品名里才写「土豆」），所以用食材库里的真名来查
    result = tools.search_ingredients(db_session, keyword="马铃薯")

    assert result["total"] >= 1
    potato = result["items"][0]
    assert "马铃薯" in potato["名称"]
    # 营养值、可食部、单价、来源都要带上：模型据此作答，用户据此核对
    assert potato["每100克可食部"]["能量_千卡"]
    assert potato["单价_元每公斤市品"]
    assert potato["数据来源"]
    assert 0 < float(potato["可食部比例"]) <= 1


def test_get_dish_recipe_returns_items_and_nutrition(db_session: Session) -> None:
    result = tools.get_dish_recipe(db_session, dish_name="宫保鸡丁")

    assert result["菜品"] == "宫保鸡丁"
    assert result["配方食材"], "配方里应当有食材用量"
    assert result["配方食材"][0]["ingredient_name"]
    assert result["配方食材"][0]["quantity_per_serving_g"]
    assert result["配方调味料"] is not None
    assert result["单份营养"] is not None
    assert result["单份营养"]["energy_kcal"]


def test_menu_day_reports_plan_and_nutrition(db_session: Session, actor) -> None:
    """某天的菜单：种子历史里必有一天能查出来。"""
    result = tools.get_menu_day(db_session, on_date=tools.today().isoformat())

    assert result["日期"] == tools.today().isoformat()
    assert result["菜单是否已确认"] is True
    assert result["供应的菜"], "今天的菜单应当有菜"
    first = result["供应的菜"][0]
    assert first["菜品"]
    assert first["单份能量_千卡"]


def test_menu_day_rejects_a_bad_date(db_session: Session) -> None:
    """日期解析不了就说清楚格式，不猜一个日子。"""
    with pytest.raises(Exception) as error:
        tools.get_menu_day(db_session, on_date="下周三")

    assert "YYYY-MM-DD" in str(error.value)


def test_dashboard_returns_four_metric_groups(db_session: Session) -> None:
    result = tools.get_dashboard(db_session, days=14)

    assert result["统计天数"] == 14
    for key in ("汇总", "达标率", "人均摄入", "剩餐与浪费"):
        assert result[key], f"{key} 不该为空"
    assert "指南" in result["口径提示"]


def test_recent_collections_list_real_logs(db_session: Session) -> None:
    result = tools.list_recent_collections(db_session, days=7)

    assert result["total"] >= 1
    row = result["items"][0]
    assert row["日期"]
    assert row["就餐人次"] > 0
    assert row["食用油_克"]


# ---------------------------------------------------------------------------
# 对话层：用脚本化的 provider 验编排
# ---------------------------------------------------------------------------
def test_chat_runs_the_tool_then_answers(db_session: Session, actor) -> None:
    scripted = ScriptedProvider(
        [
            _call("search_ingredients", '{"keyword": "马铃薯"}'),
            providers.ProviderReply(text="马铃薯每 100 克可食部约 77 千卡，数据来自演示成分表。"),
        ]
    )

    reply = service.chat(
        db_session,
        actor=actor,
        payload=ChatRequest(message="马铃薯的营养是多少？"),
        provider=scripted,
    )

    assert "马铃薯" in reply.reply
    assert reply.rounds == 2
    assert len(reply.tool_calls) == 1
    trace = reply.tool_calls[0]
    assert trace.name == "search_ingredients" and trace.ok is True
    assert "返回" in trace.summary
    # 工具结果真的回给了模型：第二轮的消息里带上了库里查出来的食材名
    second_round = scripted.calls[1]
    tool_messages = [message for message in second_round if message.get("role") == "tool"]
    assert tool_messages and "马铃薯" in tool_messages[0]["content"]


def test_chat_history_is_passed_along(db_session: Session, actor) -> None:
    scripted = ScriptedProvider([providers.ProviderReply(text="好的")])

    service.chat(
        db_session,
        actor=actor,
        payload=ChatRequest(
            message="那蛋白质呢？",
            history=[ChatTurn(role="user", content="土豆的营养是多少？")],
        ),
        provider=scripted,
    )

    roles = [message["role"] for message in scripted.calls[0]]
    assert roles == ["system", "user", "user"]
    assert "蛋白质" in scripted.calls[0][-1]["content"]


def test_unknown_tool_is_reported_back_instead_of_crashing(db_session: Session, actor) -> None:
    scripted = ScriptedProvider(
        [
            _call("write_something", "{}"),
            providers.ProviderReply(text="我没有这个能力。"),
        ]
    )

    reply = service.chat(
        db_session, actor=actor, payload=ChatRequest(message="帮我删掉这道菜"), provider=scripted
    )

    assert reply.tool_calls[0].ok is False
    assert "没有名为 write_something 的工具" in (reply.tool_calls[0].error or "")


def test_business_error_from_a_tool_is_handed_to_the_model(db_session: Session, actor) -> None:
    """工具报错（例如菜名找不到）不该断掉整轮对话，要回给模型让它改。"""
    scripted = ScriptedProvider(
        [
            _call("get_dish_recipe", '{"dish_name": "不存在的菜"}'),
            providers.ProviderReply(text="菜品库里没有这道菜。"),
        ]
    )

    reply = service.chat(
        db_session, actor=actor, payload=ChatRequest(message="这道菜怎么做？"), provider=scripted
    )

    assert reply.tool_calls[0].ok is False
    assert "没有找到" in (reply.tool_calls[0].error or "")
    assert reply.reply == "菜品库里没有这道菜。"


def test_chat_stops_at_the_round_limit(db_session: Session, actor) -> None:
    """模型一直要调工具时，兜住并如实说明「没查完」，不要无限循环。"""
    scripted = ScriptedProvider([_call("get_dashboard", "{}") for _ in range(10)])

    reply = service.chat(
        db_session, actor=actor, payload=ChatRequest(message="把所有数据都给我"), provider=scripted
    )

    assert reply.truncated is True
    assert reply.rounds == service.get_settings().assistant_max_tool_rounds
    assert "没查完" in reply.reply


# ---------------------------------------------------------------------------
# 接口
# ---------------------------------------------------------------------------
def test_status_says_not_configured_without_a_model(as_recorder: TestClient) -> None:
    """没配模型时如实说是「还没接模型」，而不是给一个点了没反应的输入框。"""
    body = as_recorder.get(f"{BASE}/status").json()

    assert body["enabled"] is False
    assert "ASSISTANT_BASE_URL" in body["note"]
    assert len(body["tools"]) >= 5


def test_chat_without_a_model_explains_how_to_configure(as_recorder: TestClient) -> None:
    response = as_recorder.post(f"{BASE}/chat", json={"message": "今天吃什么？"})

    assert response.status_code == 503
    assert "ASSISTANT_BASE_URL" in response.json()["message"]


def test_chat_endpoint_returns_the_answer(
    as_recorder: TestClient, install_provider: Callable[[ScriptedProvider], ScriptedProvider]
) -> None:
    install_provider(
        ScriptedProvider(
            [
                _call("get_menu_day", "{}"),
                providers.ProviderReply(text="今天的菜单我已经查到了。"),
            ]
        )
    )

    response = as_recorder.post(f"{BASE}/chat", json={"message": "今天吃什么？"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["reply"] == "今天的菜单我已经查到了。"
    assert body["tool_calls"][0]["name"] == "get_menu_day"
    assert body["model"] == "scripted-model"


def test_assistant_requires_login(client: TestClient) -> None:
    assert client.get(f"{BASE}/status").status_code == 401
    assert client.post(f"{BASE}/chat", json={"message": "你好"}).status_code == 401


def test_school_admin_can_ask_read_only_questions(
    as_school_admin: TestClient,
    install_provider: Callable[[ScriptedProvider], ScriptedProvider],
) -> None:
    """学校管理方本来就是只读观察者，只读的助手对他们同样开放。"""
    install_provider(
        ScriptedProvider([providers.ProviderReply(text="最近 14 天食盐日均 4.6 克。")])
    )

    body = as_school_admin.post(f"{BASE}/chat", json={"message": "最近盐用超了吗？"}).json()

    assert body["reply"]
    assert body["tool_calls"] == []


def test_reply_is_a_structured_object(db_session: Session, actor) -> None:
    """响应结构稳定：界面据此渲染工具进度与最终回答。"""
    scripted = ScriptedProvider([providers.ProviderReply(text="好")])

    reply = service.chat(
        db_session, actor=actor, payload=ChatRequest(message="你好"), provider=scripted
    )

    assert isinstance(reply, ChatReply)
    assert reply.model == "scripted-model"
    assert reply.truncated is False

"""AI 助手的行为约定。

这里**不调用真实模型**：模型是外部服务，测它等于测别人的接口。
所以用例分三层——

- **工具层**用真实数据库：查出来的必须是库里种着的食材、菜品、菜单与指标；
- **对话层**注入一个照着剧本回答的 provider：验的是我们自己的东西——
  工具调用怎么派发、业务错误怎么回给模型、轮次上限会不会兜住、未配置模型时是否如实说；
- **写闸门**是本模块的重点：助手**不能**直接写库，只能落一条待确认方案，
  人点了确认才执行；确认之后留痕要能看出这条数据是「助手提议、本人确认」来的。

真实模型的连通性只能在部署环境里手动验（配置 ASSISTANT_* 之后问一句「今天吃什么」）。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import date, timedelta
from typing import Any
from uuid import UUID

import pytest
from app.core.errors import BusinessRuleError
from app.db.session import get_session_factory
from app.modules.assistant import providers, repository, service, tools
from app.modules.assistant.router import get_chat_provider
from app.modules.assistant.schemas import ChatRequest
from app.modules.audit.models import AuditLog
from app.modules.auth.repository import get_by_username
from app.modules.auth.service import to_auth_user
from app.modules.collection import service as collection_service
from app.modules.dish import service as dish_service
from app.modules.dish.models import Dish
from app.modules.ingredient.models import Ingredient
from app.modules.nutrition.models import DishNutrition
from app.modules.recommendation import repository as recommendation_repository
from app.modules.recommendation import service as recommendation_service
from app.shared.enums import (
    AssistantProposalStatus,
    AuditAction,
    MealType,
    NutrientCaliber,
    SuggestionStatus,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from tests.helpers import today_local

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


@pytest.fixture(autouse=True)
def cleanup_assistant_rows() -> Iterator[None]:
    """用例造出来的助手数据（含确认后真的建出来的食材/菜品）用完就删。

    这些行会留在开发库里影响后续用例与演示；按名字前缀能安全地只删自己造的。
    **顺序不能反**：营养结果与配方都以外键指着菜品/食材（RESTRICT），
    先删菜品会报外键冲突——实测踩到过。营养结果 → 菜品（配方随菜品 CASCADE）→ 食材。
    """
    yield
    with get_session_factory()() as session:
        dish_ids = list(session.scalars(select(Dish.id).where(Dish.name.like("助手测试%"))))
        if dish_ids:
            session.execute(delete(DishNutrition).where(DishNutrition.dish_id.in_(dish_ids)))
        session.execute(delete(Dish).where(Dish.name.like("助手测试%")))
        session.execute(delete(Ingredient).where(Ingredient.name.like("助手测试%")))
        session.commit()


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

    def stream(self, *, messages, tools):  # type: ignore[no-untyped-def]
        """按剧本流式回答：文字分两段吐，最后一块带上完整回复（含工具调用）。"""
        reply = self.complete(messages=messages, tools=tools)
        if reply.text:
            half = max(1, len(reply.text) // 2)
            yield providers.StreamChunk(text=reply.text[:half])
            yield providers.StreamChunk(text=reply.text[half:])
        yield providers.StreamChunk(reply=reply)


def _call(name: str, arguments: str = "{}", call_id: str = "call-1") -> providers.ProviderReply:
    return providers.ProviderReply(
        text="",
        tool_calls=[providers.ProviderToolCall(id=call_id, name=name, arguments=arguments)],
    )


@pytest.fixture
def install_provider(api_app: FastAPI) -> Iterator[Callable[[ScriptedProvider], ScriptedProvider]]:
    """把接口用的 provider 换成脚本化实现，用例结束后摘掉覆盖。"""

    def _install(provider: ScriptedProvider) -> ScriptedProvider:
        api_app.dependency_overrides[get_chat_provider] = lambda: provider
        return provider

    yield _install
    api_app.dependency_overrides.pop(get_chat_provider, None)


@pytest.fixture(autouse=True)
def forbid_real_model(api_app: FastAPI) -> Iterator[None]:
    """默认不给任何用例碰真实模型。

    本地 `.env` 里配着模型端点（演示要用），一旦哪个用例忘了注入脚本化的 provider，
    它就会真的去打网络——既花用户的钱，结果也不可复现。所以默认装一个「一调就报错」的实现，
    需要真行为的用例再用 `install_provider` 覆盖它。
    """

    class _Forbidden:
        name = "forbidden"
        model = None

        def complete(self, *, messages, tools):  # type: ignore[no-untyped-def]
            raise AssertionError(
                "测试里不许调用真实模型，请用 install_provider 注入脚本化 provider"
            )

        def stream(self, *, messages, tools):  # type: ignore[no-untyped-def]
            raise AssertionError(
                "测试里不许调用真实模型，请用 install_provider 注入脚本化 provider"
            )

    api_app.dependency_overrides[get_chat_provider] = lambda: _Forbidden()
    yield
    api_app.dependency_overrides.pop(get_chat_provider, None)


def _ask(session: Session, actor, scripted: ScriptedProvider, message: str):
    return service.chat(
        session, actor=actor, payload=ChatRequest(message=message), provider=scripted
    )


# ---------------------------------------------------------------------------
# 写闸门：这是模块 21 的核心
# ---------------------------------------------------------------------------
def test_call_api_only_allows_read_paths() -> None:
    """白名单是只读的：全是 GET、没有占位符、不含助手自己的接口。

    这条盯的是「通用出口别变成后门」——它是唯一一个能碰到「没被包装成工具」的接口的入口，
    所以必须由代码保证只读，而不是靠提示词说「你只能读」。
    """
    paths = tools.read_api_paths()

    assert len(paths) >= 15, "白名单不该是空的或只有两三条"
    assert all(path.startswith("/api/v1/") for path in paths)
    assert all("{" not in path for path in paths), "带占位符的单条查询不收（现有工具已覆盖）"
    assert not any("assistant" in path for path in paths), "不给自己套娃"
    for forbidden in (
        "/api/v1/menu-plan/generate",
        "/api/v1/menu-plan/sync",
        "/api/v1/forecast/run",
    ):
        assert forbidden not in paths, "写接口一个都不该出现在白名单里"


def test_call_api_refuses_a_path_outside_the_allowlist(db_session: Session, actor) -> None:
    """不在白名单里的路径直接拒绝，并把可用清单一并给它——好让它自己改。"""
    with pytest.raises(BusinessRuleError) as error:
        tools.call_api(db_session, actor=actor, path="/api/v1/menu-plan/generate")

    message = str(error.value)
    assert "只允许只读查询" in message
    assert "/api/v1/dashboard/summary" in message


def test_call_api_reaches_endpoints_the_tools_do_not_cover(db_session: Session, actor) -> None:
    """真正兜底的地方：现有工具没覆盖、但接口里有的查询，当场就能查。"""
    factors = tools.call_api(
        db_session,
        actor=actor,
        path="/api/v1/calibration/factors",
        params={"on_date": today_local().isoformat()},
    )
    assert factors["接口"] == "/api/v1/calibration/factors"
    assert isinstance(factors["结果"], (list, dict))

    summary = tools.call_api(
        db_session, actor=actor, path="/api/v1/dashboard/summary", params={"days": 7}
    )
    assert summary["结果"], "看板汇总应当有数据"


def test_call_api_uses_the_current_user_identity(db_session: Session, actor) -> None:
    """以当前用户的身份调：接口自己的角色校验会真的跑一遍，不存在「助手有特权」。"""
    school = to_auth_user(get_by_username(db_session, "school"))

    result = tools.call_api(db_session, actor=school, path="/api/v1/meta/enums")

    assert result["结果"], "只读接口对只读角色同样开放"


def test_call_api_flags_an_empty_result(db_session: Session, actor) -> None:
    """空结果要明说，并劝它别一个日期一个日期地扫——实测模型在这上面烧掉过整轮预算。"""
    result = tools.call_api(
        db_session,
        actor=actor,
        path="/api/v1/collection/logs",
        params={"start": "2030-01-01", "end": "2030-01-02"},
    )

    assert "空结果" in str(result["说明"])
    assert "别一个日期一个日期地扫" in str(result["说明"])


def test_list_read_apis_gives_paths_with_their_parameters() -> None:
    """把「路径 + 必填/可选参数」一次给全：模型盲试参数会把轮次预算烧光（实测踩到）。"""
    listing = tools.list_read_apis(None, prefix="calibration")

    rows = {row["路径"]: row for row in listing["接口"]}
    assert rows["/api/v1/calibration/candidates"]["必填参数"] == ["on_date"]
    assert rows["/api/v1/calibration/comparison"]["必填参数"] == ["dish_id", "on_date"]
    assert "meal_type" in rows["/api/v1/calibration/candidates"]["可选参数"]


def test_call_api_error_message_names_the_required_parameters(db_session: Session, actor) -> None:
    """参数错了要把「这个接口需要什么」一并说出来，让它一次改对。"""
    with pytest.raises(BusinessRuleError) as error:
        tools.call_api(db_session, actor=actor, path="/api/v1/calibration/factors", params={})

    message = str(error.value)
    assert "on_date" in message
    assert "必填" in message


def test_repeated_calls_to_one_read_endpoint_are_cut_off(db_session: Session, actor) -> None:
    """同一个只读接口一轮里最多连查 3 次：模型曾靠换日期扫，把轮次预算烧光还没结论。"""
    scripted = ScriptedProvider(
        [
            _call(
                "call_api",
                '{"path": "/api/v1/calibration/candidates", "params": {"on_date": "2026-10-15"}}',
                "c1",
            ),
            _call(
                "call_api",
                '{"path": "/api/v1/calibration/candidates", "params": {"on_date": "2026-10-16"}}',
                "c2",
            ),
            _call(
                "call_api",
                '{"path": "/api/v1/calibration/candidates", "params": {"on_date": "2026-10-17"}}',
                "c3",
            ),
            _call(
                "call_api",
                '{"path": "/api/v1/calibration/candidates", "params": {"on_date": "2026-10-18"}}',
                "c4",
            ),
            providers.ProviderReply(text="我先看过的几天里都没有候选。"),
        ]
    )

    reply = _ask(db_session, actor, scripted, "这周该抽哪几道菜？")

    calls = [trace for trace in reply.tool_calls if trace.name == "call_api"]
    assert len(calls) == 4
    assert calls[-1].ok is False
    assert "已经查了 3 次" in (calls[-1].error or "")
    assert "问他想看哪一天" in (calls[-1].error or "")


def test_write_tools_cannot_bypass_confirmation() -> None:
    """结构上的保证：读工具不带执行入口，写工具必须「出方案 + 执行」两步俱全。

    这条不靠提示词自律——`execute` 只在确认路径上被调用。
    """
    tools.assert_write_boundary()

    write_tools = [tool for tool in tools.TOOLS if not tool.read_only]
    assert {tool.name for tool in write_tools} >= {
        "create_ingredient",
        "update_ingredient",
        "deactivate_ingredient",
        "create_dish_with_recipe",
        "update_dish",
        "deactivate_dish",
    }
    read_tools = [tool for tool in tools.TOOLS if tool.read_only]
    assert len(read_tools) >= 6

    # 撤回专用的工具不给模型看：撤回必须是「用户点了按钮」的结果，
    # 不能变成模型自己的一次自由发挥
    offered = {item["function"]["name"] for item in tools.tool_payload()}
    assert {"reactivate_ingredient", "reactivate_dish"} <= set(tools.TOOLS_BY_NAME)
    assert not {"reactivate_ingredient", "reactivate_dish"} & offered
    # call_api 是只读工具，对模型可见
    assert "call_api" in offered
    assert tools.TOOLS_BY_NAME["call_api"].read_only is True


def test_write_tool_only_creates_a_pending_proposal(db_session: Session, actor) -> None:
    """模型调用写工具时，**一个字节的业务数据都不写**，只落一条待确认方案。"""
    scripted = ScriptedProvider(
        [
            _call(
                "create_ingredient",
                '{"name": "助手测试西兰花", "category": "VEGETABLE", "data_source": "助手测试来源",'
                ' "energy_kcal": "36", "unit_price": "6.0"}',
            ),
            providers.ProviderReply(text="我准备好了方案，请你确认。"),
        ]
    )

    reply = _ask(db_session, actor, scripted, "帮我建一个食材：助手测试西兰花")

    assert reply.reply == "我准备好了方案，请你确认。"
    assert len(reply.proposals) == 1
    proposal = reply.proposals[0]
    assert proposal.status is AssistantProposalStatus.PENDING
    assert proposal.title == "新增食材：助手测试西兰花"
    assert "助手测试来源" in proposal.summary

    # 库里还没有这条食材——这就是「待确认」的含义
    assert db_session.scalar(select(Ingredient).where(Ingredient.name == "助手测试西兰花")) is None
    # 模型拿到的工具结果是「待用户确认」，不是「已建好」
    tool_message = next(m for m in scripted.calls[1] if m.get("role") == "tool")
    assert "待用户确认" in tool_message["content"]


def test_confirm_executes_the_write_and_marks_the_audit_trail(db_session: Session, actor) -> None:
    """人点确认之后才真正写库，并且留痕里能看出是「助手提议、本人确认」。"""
    scripted = ScriptedProvider(
        [
            _call(
                "create_ingredient",
                '{"name": "助手测试燕麦", "category": "GRAIN", "data_source": "助手测试来源",'
                ' "energy_kcal": "377", "unit_price": "5.5"}',
            ),
            providers.ProviderReply(text="请确认。"),
        ]
    )
    reply = _ask(db_session, actor, scripted, "建一个食材：助手测试燕麦")
    proposal_id = reply.proposals[0].id

    confirmed = service.confirm_proposal(db_session, proposal_id=UUID(proposal_id), actor=actor)

    assert confirmed.status is AssistantProposalStatus.CONFIRMED
    assert confirmed.result is not None and confirmed.result["名称"] == "助手测试燕麦"
    created = db_session.scalar(select(Ingredient).where(Ingredient.name == "助手测试燕麦"))
    assert created is not None and str(created.unit_price) == "5.50"

    # 留痕：操作人是本人，但备注里写明是助手提议的
    entry = db_session.scalar(
        select(AuditLog)
        .where(AuditLog.entity_id == str(created.id), AuditLog.action == AuditAction.CREATE)
        .order_by(AuditLog.created_at.desc())
    )
    assert entry is not None
    assert entry.actor_id == actor.id
    assert entry.note is not None and "AI 助手" in entry.note


def test_cancel_changes_nothing(db_session: Session, actor) -> None:
    scripted = ScriptedProvider(
        [
            _call(
                "create_ingredient",
                '{"name": "助手测试弃用食材", "category": "OTHER", "data_source": "助手测试来源"}',
            ),
            providers.ProviderReply(text="请确认。"),
        ]
    )
    reply = _ask(db_session, actor, scripted, "建一个食材")
    cancelled = service.cancel_proposal(
        db_session, proposal_id=UUID(reply.proposals[0].id), actor=actor
    )

    assert cancelled.status is AssistantProposalStatus.CANCELLED
    assert (
        db_session.scalar(select(Ingredient).where(Ingredient.name == "助手测试弃用食材")) is None
    )


def test_a_proposal_cannot_be_confirmed_twice(db_session: Session, actor) -> None:
    scripted = ScriptedProvider(
        [
            _call(
                "create_ingredient",
                '{"name": "助手测试重复确认", "category": "OTHER", "data_source": "助手测试来源"}',
            ),
            providers.ProviderReply(text="请确认。"),
        ]
    )
    reply = _ask(db_session, actor, scripted, "建一个食材")
    proposal_id = UUID(reply.proposals[0].id)
    service.confirm_proposal(db_session, proposal_id=proposal_id, actor=actor)

    with pytest.raises(Exception) as error:
        service.confirm_proposal(db_session, proposal_id=proposal_id, actor=actor)

    assert "已经" in str(error.value)


def test_failed_execution_is_recorded_instead_of_lost(db_session: Session, actor) -> None:
    """执行失败也要落痕：方案留在 FAILED 并写清原因，而不是静默什么都没发生。"""
    scripted = ScriptedProvider(
        [
            _call(
                "create_ingredient",
                '{"name": "助手测试味道不对", "category": "NOT_A_CATEGORY",'
                ' "data_source": "助手测试来源"}',
            ),
            providers.ProviderReply(text="请确认。"),
        ]
    )
    reply = _ask(db_session, actor, scripted, "建一个食材")
    proposal_id = UUID(reply.proposals[0].id)

    failed = service.confirm_proposal(db_session, proposal_id=proposal_id, actor=actor)

    assert failed.status is AssistantProposalStatus.FAILED
    assert failed.error


def test_other_peoples_proposals_cannot_be_confirmed(db_session: Session, actor) -> None:
    """别人那条对话里的方案，只能由他本人确认。"""
    scripted = ScriptedProvider(
        [
            _call(
                "create_ingredient",
                '{"name": "助手测试别人的", "category": "OTHER", "data_source": "助手测试来源"}',
            ),
            providers.ProviderReply(text="请确认。"),
        ]
    )
    reply = _ask(db_session, actor, scripted, "建一个食材")

    other = to_auth_user(get_by_username(db_session, "canteen"))
    with pytest.raises(Exception) as error:
        service.confirm_proposal(db_session, proposal_id=UUID(reply.proposals[0].id), actor=other)

    assert "本人确认" in str(error.value)


def test_dish_write_tool_reports_ingredients_missing_from_the_library(
    db_session: Session, actor
) -> None:
    """配方里的食材对不上要当场说清楚——等人确认之后才发现就晚了。"""
    scripted = ScriptedProvider(
        [
            _call(
                "create_dish_with_recipe",
                '{"name": "助手测试菜", "category": "VEGETABLE", "cooking_method": "STIR_FRY",'
                ' "standard_serving_g": "150",'
                ' "recipe_items": [{"ingredient_name": "并不存在的食材",'
                ' "quantity_per_serving_g": "100"}]}',
            ),
            providers.ProviderReply(text="请确认。"),
        ]
    )

    reply = _ask(db_session, actor, scripted, "帮我加一道菜")

    preview = reply.proposals[0].preview
    hints = " ".join(preview["提示"])
    assert "并不存在的食材" in hints
    assert preview["配方食材"][0]["库里匹配"] is None
    assert db_session.scalar(select(Dish).where(Dish.name == "助手测试菜")) is None, (
        "待确认阶段不该建出菜品"
    )


# ---------------------------------------------------------------------------
# 一句话录一餐
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# 排菜单与同步：这是用户最先问到的一处缺口
# ---------------------------------------------------------------------------
def test_generate_menu_plan_answers_in_one_call(
    as_recorder: TestClient, db_session: Session
) -> None:
    """「排一下菜单」应当一次调用就出结果：菜品 + 预测份数 + 差距 + 采购汇总。

    这件事只产出建议，不改当天的菜单与采集，所以不需要人确认就能跑。
    """
    target = _free_day(db_session)
    result = tools.generate_menu_plan(db_session, on_date=target.isoformat(), meal_type="LUNCH")

    assert result["日期"] == target.isoformat()
    assert result["菜品"], "排出来的菜单不该是空的"
    first = result["菜品"][0]
    assert first["菜品"] and first["预测份数"]
    assert result["与营养目标的差距"] and result["推荐理由"]
    assert result["采购"]["项数"] > 0
    # 没同步之前，当天的菜单日不该被写进去
    assert (
        collection_service.has_collection(db_session, on_date=target, meal_type=MealType.LUNCH)
        is False
    )
    assert tools._menu_snapshot(db_session, on_date=target, meal_type=MealType.LUNCH) == [], (
        "排菜单只出方案，不写菜单日"
    )


def test_sync_menu_plan_requires_a_generated_plan_first(
    as_recorder: TestClient, db_session: Session
) -> None:
    """还没排过就要同步：说清先做什么，而不是报一个看不懂的错。"""
    target = _free_day(db_session)

    with pytest.raises(BusinessRuleError) as error:
        tools.sync_menu_plan_draft(db_session, on_date=target.isoformat(), meal_type="LUNCH")

    assert "还没有生成过菜单" in str(error.value)
    assert "generate_menu_plan" in str(error.value)


def test_sync_menu_plan_writes_the_day_and_can_be_reverted(
    as_recorder: TestClient, db_session: Session, actor
) -> None:
    """同步之后采集页与大屏都会跟着变；撤回要把菜单退回原样、推荐记录也回到待确认。"""
    target = _free_day(db_session)
    tools.generate_menu_plan(db_session, on_date=target.isoformat(), meal_type="LUNCH")

    draft = tools.sync_menu_plan_draft(db_session, on_date=target.isoformat(), meal_type="LUNCH")
    assert draft["preview"]["菜品"], "方案里要列出将写入的菜"
    outcome = tools.sync_menu_plan_execute(db_session, draft["payload"], actor=actor)
    assert outcome.result["菜品数"] > 0

    db_session.expire_all()
    planned = tools._menu_snapshot(db_session, on_date=target, meal_type=MealType.LUNCH)
    assert len(planned) == outcome.result["菜品数"]
    suggestion_id = UUID(str(draft["payload"]["suggestion_id"]))
    assert (
        recommendation_repository.get_suggestion(db_session, suggestion_id).status
        is SuggestionStatus.ACCEPTED
    )

    assert [step.tool for step in outcome.undo] == ["restore_menu_day", "reopen_suggestion"]
    for step in outcome.undo:
        tools.TOOLS_BY_NAME[step.tool].execute(db_session, step.payload, actor=actor)

    db_session.expire_all()
    assert tools._menu_snapshot(db_session, on_date=target, meal_type=MealType.LUNCH) == []
    assert (
        recommendation_repository.get_suggestion(db_session, suggestion_id).status
        is SuggestionStatus.PENDING
    ), "菜单退回去了，推荐记录也该回到待确认，否则两处状态对不上"


def test_sync_menu_plan_refuses_days_that_are_already_collected(
    as_recorder: TestClient, db_session: Session, actor
) -> None:
    target = _free_day(db_session)
    tools.generate_menu_plan(db_session, on_date=target.isoformat(), meal_type="LUNCH")
    collected = tools.save_collection_draft(
        db_session,
        on_date=target.isoformat(),
        meal_type="LUNCH",
        diner_count=300,
        dishes=[{"dish_name": "米饭", "servings": "280"}],
    )
    tools.save_collection_execute(db_session, collected["payload"], actor=actor)

    with pytest.raises(BusinessRuleError) as error:
        tools.sync_menu_plan_draft(db_session, on_date=target.isoformat(), meal_type="LUNCH")

    assert "已经录过采集" in str(error.value)


def _fresh_day(offset: int = 30) -> date:
    """种子历史之外的一天：这些用例会往将来写菜单与采集，不能落在演示数据上。"""
    return today_local() + timedelta(days=offset)


def _free_day(session: Session, *, start: int = 40, span: int = 20) -> date:
    """找一个**既没有采集也没有菜单**的将来日期。

    写死偏移踩过两次：`+41` 被端到端用例写过采集，于是「先排菜单再同步」的用例
    在同步那一步拿到的是「已经录过采集」，跟它要验的东西完全不相干。
    这些用例需要的是「一个干净的将来日子」，那就按这个条件去找，而不是猜一个数字。
    """
    for offset in range(start, start + span):
        day = today_local() + timedelta(days=offset)
        if collection_service.has_collection(session, on_date=day, meal_type=MealType.LUNCH):
            continue
        if tools._menu_snapshot(session, on_date=day, meal_type=MealType.LUNCH):
            continue
        # 有推荐记录也不行：本模块前面的用例会往将来日期排菜单，
        # 复用同一天会让「还没排过」这类断言拿到反例
        if recommendation_service.latest_suggestion_id(
            session, on_date=day, meal_type=MealType.LUNCH
        ):
            continue
        return day
    raise AssertionError(f"在 +{start}~+{start + span} 天里找不到干净的日子")


def test_save_collection_draft_shows_what_will_be_written(
    as_recorder: TestClient, db_session: Session
) -> None:
    """录用采集的预览要摆全：日期、人次、油盐糖、每道菜多少份；对不上的菜名要点出来。"""
    target = _free_day(db_session)
    draft = tools.save_collection_draft(
        db_session,
        on_date=target.isoformat(),
        meal_type="LUNCH",
        diner_count=880,
        oil_total_g="5200",
        salt_total_g="1800",
        dishes=[
            {"dish_name": "米饭", "servings": "800"},
            {"dish_name": "并不存在的菜", "servings": "100"},
        ],
    )

    assert draft["preview"]["将录入"]["就餐人次"] == 880
    assert draft["preview"]["将录入"]["食用油_克"] == "5200"
    assert [row["菜品"] for row in draft["preview"]["菜品"]] == ["米饭"]
    assert any("并不存在的菜" in hint for hint in draft["preview"]["提示"])
    assert any("重算营养" in hint for hint in draft["preview"]["提示"])
    assert (
        collection_service.has_collection(db_session, on_date=target, meal_type=MealType.LUNCH)
        is False
    ), "待确认阶段不该有采集记录"


def test_save_collection_execute_then_revert_discards_the_log(
    as_recorder: TestClient, db_session: Session, actor
) -> None:
    """原来没有采集记录时，撤回 = 把这条误录整份丢掉（连人均营养结果）。"""
    target = _free_day(db_session)
    draft = tools.save_collection_draft(
        db_session,
        on_date=target.isoformat(),
        meal_type="LUNCH",
        diner_count=500,
        oil_total_g="3000",
        salt_total_g="900",
        dishes=[{"dish_name": "米饭", "servings": "450"}],
    )
    outcome = tools.save_collection_execute(db_session, draft["payload"], actor=actor)

    assert outcome.result["菜品数"] == 1
    assert collection_service.has_collection(db_session, on_date=target, meal_type=MealType.LUNCH)
    db_session.expire_all()
    per_capita = db_session.scalars(
        select(DishNutrition).where(
            DishNutrition.date == target,
            DishNutrition.caliber == NutrientCaliber.PER_CAPITA,
        )
    ).all()
    assert per_capita, "保存之后应当有人均口径的营养结果"

    assert outcome.undo and outcome.undo[0].tool == "restore_collection"
    tools.TOOLS_BY_NAME["restore_collection"].execute(
        db_session, outcome.undo[0].payload, actor=actor
    )

    db_session.expire_all()
    assert (
        collection_service.has_collection(db_session, on_date=target, meal_type=MealType.LUNCH)
        is False
    ), "撤回之后不该还留着这条采集"
    left = db_session.scalars(
        select(DishNutrition).where(
            DishNutrition.date == target,
            DishNutrition.caliber == NutrientCaliber.PER_CAPITA,
        )
    ).all()
    assert left == [], "人均结果离开采集就没有依据，必须一起清掉（否则看板会算错）"


def test_save_collection_over_an_existing_log_reverts_to_the_old_values(
    as_recorder: TestClient, db_session: Session, actor
) -> None:
    """原来就有采集时，撤回 = 写回原来那条（人次、油盐糖、份数都要回去）。"""
    target = _free_day(db_session)
    first = tools.save_collection_draft(
        db_session,
        on_date=target.isoformat(),
        meal_type="LUNCH",
        diner_count=500,
        oil_total_g="3000",
        salt_total_g="900",
        dishes=[{"dish_name": "米饭", "servings": "450"}],
    )
    tools.save_collection_execute(db_session, first["payload"], actor=actor)

    second = tools.save_collection_draft(
        db_session,
        on_date=target.isoformat(),
        meal_type="LUNCH",
        diner_count=999,
        oil_total_g="9999",
        salt_total_g="1999",
        dishes=[{"dish_name": "米饭", "servings": "900"}],
    )
    assert any("整份覆盖" in hint for hint in second["preview"]["提示"])
    outcome = tools.save_collection_execute(db_session, second["payload"], actor=actor)
    assert outcome.undo[0].payload["previous"] is not None

    tools.TOOLS_BY_NAME["restore_collection"].execute(
        db_session, outcome.undo[0].payload, actor=actor
    )
    db_session.expire_all()
    sheet = collection_service.build_sheet(db_session, on_date=target, meal_type=MealType.LUNCH)
    assert sheet.diner_count == 500
    assert str(sheet.oil_total_g) == "3000.00"
    assert [row.servings_produced for row in sheet.dishes if row.selected] == ["450.00"]


def test_set_menu_day_refuses_days_that_are_already_collected(
    as_recorder: TestClient, db_session: Session, actor
) -> None:
    """已经录过采集的日子不能再单独改菜单——那一天的菜单以实际供应为准。"""
    target = _free_day(db_session)
    draft = tools.save_collection_draft(
        db_session,
        on_date=target.isoformat(),
        meal_type="LUNCH",
        diner_count=400,
        dishes=[{"dish_name": "米饭", "servings": "380"}],
    )
    tools.save_collection_execute(db_session, draft["payload"], actor=actor)

    with pytest.raises(BusinessRuleError) as error:
        tools.set_menu_day_draft(
            db_session, on_date=target.isoformat(), meal_type="LUNCH", dish_names=["米饭"]
        )

    assert "已经录过采集" in str(error.value)
    assert "录入采集" in str(error.value)


def test_set_menu_day_writes_the_plan_and_can_be_reverted(
    as_recorder: TestClient, db_session: Session, actor
) -> None:
    """没录采集的日子可以调菜单：写进去之后采集页与大屏都会按它走，且可撤回。"""
    target = _free_day(db_session)
    before = tools.set_menu_day_draft(
        db_session, on_date=target.isoformat(), meal_type="LUNCH", dish_names=["米饭"]
    )
    assert "计划" in " ".join(before["preview"]["提示"])
    outcome = tools.set_menu_day_execute(db_session, before["payload"], actor=actor)
    assert outcome.undo[0].payload["items"] == [], "第一次改之前菜单是空的，撤回就该回到空"

    after = tools.set_menu_day_draft(
        db_session,
        on_date=target.isoformat(),
        meal_type="LUNCH",
        dish_names=["米饭", "清炒西兰花"],
    )
    outcome2 = tools.set_menu_day_execute(db_session, after["payload"], actor=actor)
    db_session.expire_all()
    assert len(tools._menu_snapshot(db_session, on_date=target, meal_type=MealType.LUNCH)) == 2

    tools.TOOLS_BY_NAME["restore_menu_day"].execute(
        db_session, outcome2.undo[0].payload, actor=actor
    )
    db_session.expire_all()
    assert len(tools._menu_snapshot(db_session, on_date=target, meal_type=MealType.LUNCH)) == 1


def test_revoke_of_a_collection_proposal_through_the_endpoint(
    as_recorder: TestClient,
    db_session: Session,
    install_provider: Callable[[ScriptedProvider], ScriptedProvider],
) -> None:
    """整条链路的收尾：让助手录一餐 → 确认 → 撤回，采集记录应当没了。"""
    target = _free_day(db_session)
    install_provider(
        ScriptedProvider(
            [
                _call(
                    "save_collection",
                    f'{{"on_date": "{target.isoformat()}", "meal_type": "LUNCH",'
                    ' "diner_count": 300, "oil_total_g": "1000", "salt_total_g": "300",'
                    ' "dishes": [{"dish_name": "米饭", "servings": "280"}]}',
                ),
                providers.ProviderReply(text="方案好了，请确认。"),
            ]
        )
    )
    created = as_recorder.post(f"{BASE}/chat", json={"message": f"把 {target} 的午餐录一下"}).json()
    assert created["proposals"][0]["title"].startswith("录入采集")

    proposal_id = created["proposals"][0]["id"]
    confirmed = as_recorder.post(f"{BASE}/proposals/{proposal_id}/confirm")
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["can_revoke"] is True

    sheet = as_recorder.get(
        f"/api/v1/collection/logs/{target.isoformat()}", params={"meal_type": "LUNCH"}
    ).json()
    assert sheet["saved"] is True and sheet["diner_count"] == 300

    reverted = as_recorder.post(f"{BASE}/proposals/{proposal_id}/revoke")
    assert reverted.status_code == 200, reverted.text
    assert reverted.json()["status"] == "REVERTED"

    after = as_recorder.get(
        f"/api/v1/collection/logs/{target.isoformat()}", params={"meal_type": "LUNCH"}
    ).json()
    assert after["saved"] is False, "撤回之后这一餐不该还留着采集记录"


# ---------------------------------------------------------------------------
# 对话落库（审计）
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# 改与删，以及撤回
# ---------------------------------------------------------------------------
def _make_ingredient(client: TestClient, name: str, **overrides: Any) -> dict:
    """用接口建一条测试用食材（走的是与人一样的录入路径）。"""
    payload = {
        "name": name,
        "category": "VEGETABLE",
        "data_source": "助手测试来源",
        "energy_kcal": "36",
        "unit_price": "6.0",
        **overrides,
    }
    response = client.post("/api/v1/ingredients", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _proposal_of(scripted: ScriptedProvider, actor, session: Session, message: str = "改一下"):
    return _ask(session, actor, scripted, message)


def test_update_ingredient_shows_before_and_after_without_writing(
    as_recorder: TestClient, db_session: Session, actor
) -> None:
    """改食材的方案要把「现在的值 → 改成什么」摆出来，而且**一个字都不写**。"""
    _make_ingredient(as_recorder, "助手测试单价菜", unit_price="6.0")

    scripted = ScriptedProvider(
        [
            _call(
                "update_ingredient",
                '{"name": "助手测试单价菜", "unit_price": "7.5"}',
            ),
            providers.ProviderReply(text="方案好了，请确认。"),
        ]
    )
    reply = _proposal_of(scripted, actor, db_session, "把助手测试单价菜的单价改成 7.5")

    preview = reply.proposals[0].preview
    assert preview["将修改"] == [{"字段": "单价_元每公斤市品", "现在": "6", "改成": "7.5"}]

    row = db_session.scalar(select(Ingredient).where(Ingredient.name == "助手测试单价菜"))
    db_session.refresh(row)
    assert str(row.unit_price) == "6.00", "待确认阶段不该写库"


def test_update_ingredient_execute_then_revoke_restores_the_value(
    as_recorder: TestClient, db_session: Session, actor
) -> None:
    """改完之后撤回，要回到原来的值。"""
    _make_ingredient(as_recorder, "助手测试回滚菜", unit_price="6.0")
    ingredient_id = db_session.scalar(
        select(Ingredient.id).where(Ingredient.name == "助手测试回滚菜")
    )

    outcome = tools.update_ingredient_execute(
        db_session,
        {"ingredient_id": str(ingredient_id), "changes": {"unit_price": "9.9"}},
        actor=actor,
    )
    db_session.expire_all()
    assert (
        str(db_session.scalar(select(Ingredient).where(Ingredient.id == ingredient_id)).unit_price)
        == "9.90"
    )
    assert outcome.undo and outcome.undo[0].tool == "update_ingredient"

    # 撤回步骤直接执行一次（界面上是点「撤回」，走的是同一条路径）
    tools.TOOLS_BY_NAME["update_ingredient"].execute(
        db_session, outcome.undo[0].payload, actor=actor
    )
    db_session.expire_all()
    assert (
        str(db_session.scalar(select(Ingredient).where(Ingredient.id == ingredient_id)).unit_price)
        == "6.00"
    )


def test_update_dish_draft_lists_fields_and_recipe(
    as_recorder: TestClient, db_session: Session
) -> None:
    """改菜品的方案要把基础字段与「原配方 → 新配方」都摆出来（这里专门盯 draft 路径）。"""
    created = _make_ingredient(as_recorder, "助手测试草案配料", energy_kcal="100")
    dish = as_recorder.post(
        "/api/v1/dishes",
        json={
            "name": "助手测试草案菜",
            "category": "VEGETABLE",
            "cooking_method": "STIR_FRY",
            "standard_serving_g": "150",
            "servings_per_pot": "10",
            "recipe": {
                "ingredients": [{"ingredient_id": created["id"], "quantity_per_serving_g": "80"}],
                "seasonings": [],
            },
        },
    )
    assert dish.status_code == 201, dish.text

    draft = tools.update_dish_draft(
        db_session,
        name="助手测试草案菜",
        standard_serving_g="180",
        recipe_items=[{"ingredient_name": "助手测试草案配料", "quantity_per_serving_g": "120"}],
    )

    assert draft["preview"]["将修改"] == [{"字段": "标准份量_克", "现在": "150", "改成": "180"}]
    assert draft["preview"]["当前配方"] == [{"食材": "助手测试草案配料", "单份用量_克": "80.000"}]
    assert draft["preview"]["新配方食材"][0]["库里匹配"] == "助手测试草案配料"
    assert any("整体替换" in hint for hint in draft["preview"]["提示"])


def test_deactivate_ingredient_reports_impact_and_can_be_reverted(
    as_recorder: TestClient, db_session: Session, actor
) -> None:
    """停用是软删除：方案里要写出影响面，撤回就是重新启用。"""
    created = _make_ingredient(as_recorder, "助手测试停用菜")
    ingredient_id = UUID(created["id"])

    draft = tools.deactivate_ingredient_draft(db_session, name="助手测试停用菜")
    assert "被引用" in draft["preview"]["将停用"]
    assert any("可以撤回" in hint for hint in draft["preview"]["提示"])

    outcome = tools.deactivate_ingredient_execute(
        db_session, {"ingredient_id": str(ingredient_id), "reason": "用例"}, actor=actor
    )
    db_session.expire_all()
    assert (
        db_session.scalar(select(Ingredient).where(Ingredient.id == ingredient_id)).is_active
        is False
    )
    assert outcome.undo and outcome.undo[0].tool == "reactivate_ingredient"

    tools.TOOLS_BY_NAME["reactivate_ingredient"].execute(
        db_session, outcome.undo[0].payload, actor=actor
    )
    db_session.expire_all()
    assert (
        db_session.scalar(select(Ingredient).where(Ingredient.id == ingredient_id)).is_active
        is True
    )


def test_update_dish_recipe_can_be_reverted(
    as_recorder: TestClient, db_session: Session, actor
) -> None:
    """改配方是整体替换，撤回要把原来那份配方放回去。"""
    created = _make_ingredient(as_recorder, "助手测试配料", energy_kcal="100")
    dish = as_recorder.post(
        "/api/v1/dishes",
        json={
            "name": "助手测试回滚菜",
            "category": "VEGETABLE",
            "cooking_method": "STIR_FRY",
            "standard_serving_g": "150",
            "servings_per_pot": "10",
            "recipe": {
                "ingredients": [{"ingredient_id": created["id"], "quantity_per_serving_g": "80"}],
                "seasonings": [],
            },
        },
    )
    assert dish.status_code == 201, dish.text
    dish_id = UUID(dish.json()["id"])

    outcome = tools.update_dish_execute(
        db_session,
        {
            "dish_id": str(dish_id),
            "changes": {},
            "recipe": {
                "ingredients": [{"ingredient_id": created["id"], "quantity_per_serving_g": "120"}],
                "seasonings": [],
            },
        },
        actor=actor,
    )
    assert outcome.undo and outcome.undo[0].payload["recipe"] is not None
    after = dish_service.get_dish_detail(db_session, dish_id)
    assert after.recipe is not None
    assert after.recipe.ingredients[0].quantity_per_serving_g == "120.000"

    tools.TOOLS_BY_NAME["update_dish"].execute(db_session, outcome.undo[0].payload, actor=actor)
    restored = dish_service.get_dish_detail(db_session, dish_id)
    assert restored.recipe is not None
    assert restored.recipe.ingredients[0].quantity_per_serving_g == "80.000"


def test_revoke_refuses_when_someone_changed_the_data_afterwards(
    as_recorder: TestClient, db_session: Session, actor
) -> None:
    """执行之后别人又改过同一条数据时，撤回要拒绝——否则会把那次改动一起抹掉。"""
    created = _make_ingredient(as_recorder, "助手测试抢改菜", unit_price="6.0")
    ingredient_id = UUID(created["id"])

    scripted = ScriptedProvider(
        [
            _call(
                "update_ingredient",
                '{"name": "助手测试抢改菜", "unit_price": "7.5"}',
            ),
            providers.ProviderReply(text="请确认。"),
        ]
    )
    reply = _proposal_of(scripted, actor, db_session, "改单价")
    proposal_id = UUID(reply.proposals[0].id)
    service.confirm_proposal(db_session, proposal_id=proposal_id, actor=actor)

    # 别人（同一个账号也行）后来又改了一次同一条数据
    as_recorder.patch(f"/api/v1/ingredients/{ingredient_id}", json={"unit_price": "8.8"})

    with pytest.raises(BusinessRuleError) as error:
        service.revoke_proposal(db_session, proposal_id=proposal_id, actor=actor)

    assert "又被改过" in str(error.value)


def test_revoke_only_applies_to_confirmed_proposals(
    as_recorder: TestClient, db_session: Session, actor
) -> None:
    """待确认的撤不了（取消即可），已撤回的不能再来一次。"""
    _make_ingredient(as_recorder, "助手测试状态菜", unit_price="6.0")
    scripted = ScriptedProvider(
        [
            _call("update_ingredient", '{"name": "助手测试状态菜", "unit_price": "7"}'),
            providers.ProviderReply(text="请确认。"),
        ]
    )
    reply = _proposal_of(scripted, actor, db_session, "改单价")
    proposal_id = UUID(reply.proposals[0].id)

    with pytest.raises(BusinessRuleError) as pending_error:
        service.revoke_proposal(db_session, proposal_id=proposal_id, actor=actor)
    assert "不能撤回" in str(pending_error.value)

    service.confirm_proposal(db_session, proposal_id=proposal_id, actor=actor)
    first = service.revoke_proposal(db_session, proposal_id=proposal_id, actor=actor)
    assert first.status is AssistantProposalStatus.REVERTED
    assert first.revoked_at is not None

    with pytest.raises(BusinessRuleError) as again:
        service.revoke_proposal(db_session, proposal_id=proposal_id, actor=actor)
    assert "已经撤回" in str(again.value)


def test_revoke_endpoint_works_for_the_owner(
    as_recorder: TestClient, install_provider: Callable[[ScriptedProvider], ScriptedProvider]
) -> None:
    as_recorder.post(
        "/api/v1/ingredients",
        json={
            "name": "助手测试接口撤回",
            "category": "VEGETABLE",
            "data_source": "助手测试来源",
            "unit_price": "6.0",
        },
    )
    install_provider(
        ScriptedProvider(
            [
                _call(
                    "update_ingredient",
                    '{"name": "助手测试接口撤回", "unit_price": "9.0"}',
                ),
                providers.ProviderReply(text="请确认。"),
            ]
        )
    )
    created = as_recorder.post(f"{BASE}/chat", json={"message": "改单价"}).json()
    proposal_id = created["proposals"][0]["id"]

    confirmed = as_recorder.post(f"{BASE}/proposals/{proposal_id}/confirm").json()
    assert confirmed["can_revoke"] is True

    reverted = as_recorder.post(f"{BASE}/proposals/{proposal_id}/revoke")
    assert reverted.status_code == 200, reverted.text
    assert reverted.json()["status"] == "REVERTED"
    assert reverted.json()["status_label"] == "已撤回"


def test_conversation_and_messages_are_persisted(db_session: Session, actor) -> None:
    scripted = ScriptedProvider([providers.ProviderReply(text="今天供应 5 道菜。")])

    reply = _ask(db_session, actor, scripted, "今天午餐吃什么？")

    conversation = repository.get_conversation(db_session, UUID(reply.conversation_id))
    assert conversation is not None
    assert conversation.title.startswith("今天午餐吃什么")
    assert conversation.user_name == actor.display_name
    messages = repository.list_messages(db_session, conversation_id=conversation.id)
    assert [message.role.value for message in messages] == ["USER", "ASSISTANT"]
    assert messages[1].content == "今天供应 5 道菜。"


def test_follow_up_question_carries_server_side_history(db_session: Session, actor) -> None:
    """接着问时，历史由服务端从库里读——客户端传什么不算数。"""
    first = ScriptedProvider(
        [_call("get_menu_day", "{}"), providers.ProviderReply(text="今天有米饭。")]
    )
    reply = _ask(db_session, actor, first, "今天午餐吃什么？")

    second = ScriptedProvider([providers.ProviderReply(text="米饭 276 千卡。")])
    service.chat(
        db_session,
        actor=actor,
        payload=ChatRequest(message="那米饭多少能量？", conversation_id=reply.conversation_id),
        provider=second,
    )

    roles = [message["role"] for message in second.calls[0]]
    assert roles == ["system", "user", "assistant", "user"]
    assert "今天有米饭。" in second.calls[0][2]["content"]


def test_cannot_continue_someone_elses_conversation(db_session: Session, actor) -> None:
    scripted = ScriptedProvider([providers.ProviderReply(text="好")])
    reply = _ask(db_session, actor, scripted, "你好")

    other = to_auth_user(get_by_username(db_session, "canteen"))
    with pytest.raises(Exception) as error:
        service.chat(
            db_session,
            actor=other,
            payload=ChatRequest(message="接着问", conversation_id=reply.conversation_id),
            provider=scripted,
        )

    assert "别人的对话" in str(error.value)


def test_conversation_list_is_scoped_by_role(db_session: Session, actor) -> None:
    """录入员只看自己的对话；管理员与学校管理方可以查阅全部（审计视角）。"""
    scripted = ScriptedProvider([providers.ProviderReply(text="好")])
    _ask(db_session, actor, scripted, "助手测试第一句")
    school_user = to_auth_user(get_by_username(db_session, "school"))
    _ask(db_session, school_user, scripted, "助手测试学校问的")

    mine = service.list_conversations(db_session, actor=actor)
    assert {row.user_name for row in mine} == {actor.display_name}

    admin = to_auth_user(get_by_username(db_session, "canteen"))
    all_rows = service.list_conversations(db_session, actor=admin)
    assert any(row.user_name == school_user.display_name for row in all_rows)


def test_conversation_detail_includes_tool_calls(db_session: Session, actor) -> None:
    scripted = ScriptedProvider(
        [_call("get_dashboard", '{"days": 7}'), providers.ProviderReply(text="看板已查。")]
    )
    reply = _ask(db_session, actor, scripted, "看看最近 7 天")

    detail = service.get_conversation(
        db_session, conversation_id=UUID(reply.conversation_id), actor=actor
    )

    assert len(detail.messages) == 2
    assert detail.messages[1].tool_calls[0].name == "get_dashboard"
    assert detail.messages[1].tool_calls[0].label == "看板指标"


# ---------------------------------------------------------------------------
# 读工具：数据必须来自真实库
# ---------------------------------------------------------------------------
def test_search_ingredients_returns_seeded_data(db_session: Session) -> None:
    # 库里叫「马铃薯」（菜品名里才写「土豆」），所以用食材库里的真名来查
    result = tools.search_ingredients(db_session, keyword="马铃薯")

    assert result["total"] >= 1
    potato = result["items"][0]
    assert "马铃薯" in potato["名称"]
    assert potato["每100克可食部"]["能量_千卡"]
    assert potato["单价_元每公斤市品"]
    assert potato["数据来源"]


def test_get_dish_recipe_returns_items_and_nutrition(db_session: Session) -> None:
    result = tools.get_dish_recipe(db_session, dish_name="宫保鸡丁")

    assert result["菜品"] == "宫保鸡丁"
    assert result["配方食材"] and result["配方食材"][0]["ingredient_name"]
    assert result["单份营养"] is not None and result["单份营养"]["energy_kcal"]


def test_menu_day_reports_plan_and_nutrition(db_session: Session) -> None:
    result = tools.get_menu_day(db_session, on_date=tools.today().isoformat())

    assert result["菜单是否已确认"] is True
    assert result["供应的菜"] and result["供应的菜"][0]["单份能量_千卡"]


def test_menu_day_rejects_a_bad_date(db_session: Session) -> None:
    with pytest.raises(Exception) as error:
        tools.get_menu_day(db_session, on_date="下周三")

    assert "YYYY-MM-DD" in str(error.value)


def test_dashboard_returns_four_metric_groups(db_session: Session) -> None:
    result = tools.get_dashboard(db_session, days=14)

    for key in ("汇总", "达标率", "人均摄入", "剩餐与浪费"):
        assert result[key], f"{key} 不该为空"


def test_recent_collections_list_real_logs(db_session: Session) -> None:
    result = tools.list_recent_collections(db_session, days=7)

    assert result["total"] >= 1
    assert result["items"][0]["就餐人次"] > 0


# ---------------------------------------------------------------------------
# 对话编排
# ---------------------------------------------------------------------------
def test_chat_runs_the_tool_then_answers(db_session: Session, actor) -> None:
    scripted = ScriptedProvider(
        [
            _call("search_ingredients", '{"keyword": "马铃薯"}'),
            providers.ProviderReply(text="马铃薯每 100 克可食部约 77 千卡。"),
        ]
    )

    reply = _ask(db_session, actor, scripted, "马铃薯的营养是多少？")

    assert reply.rounds == 2
    assert len(reply.tool_calls) == 1 and reply.tool_calls[0].ok
    tool_messages = [m for m in scripted.calls[1] if m.get("role") == "tool"]
    assert tool_messages and "马铃薯" in tool_messages[0]["content"]


def test_unknown_tool_is_reported_back_instead_of_crashing(db_session: Session, actor) -> None:
    scripted = ScriptedProvider(
        [_call("write_something", "{}"), providers.ProviderReply(text="我没有这个能力。")]
    )

    reply = _ask(db_session, actor, scripted, "帮我删掉这道菜")

    assert reply.tool_calls[0].ok is False
    assert "没有名为 write_something 的工具" in (reply.tool_calls[0].error or "")


def test_business_error_from_a_tool_is_handed_to_the_model(db_session: Session, actor) -> None:
    scripted = ScriptedProvider(
        [
            _call("get_dish_recipe", '{"dish_name": "不存在的菜"}'),
            providers.ProviderReply(text="菜品库里没有这道菜。"),
        ]
    )

    reply = _ask(db_session, actor, scripted, "这道菜怎么做？")

    assert reply.tool_calls[0].ok is False
    assert "没有找到" in (reply.tool_calls[0].error or "")


def test_chat_stops_at_the_round_limit(db_session: Session, actor) -> None:
    scripted = ScriptedProvider([_call("get_dashboard", "{}", f"c{i}") for i in range(10)])

    reply = _ask(db_session, actor, scripted, "把所有数据都给我")

    assert reply.truncated is True
    assert reply.rounds == service.get_settings().assistant_max_tool_rounds


# ---------------------------------------------------------------------------
# 接口
# ---------------------------------------------------------------------------
def test_every_model_call_carries_an_output_limit() -> None:
    """单次调用必须带上 max_tokens：回答再长用户也不会读完，而费用是实打实的。"""
    provider = providers.OpenAICompatibleProvider(
        base_url="https://example.invalid/v1",
        api_key=None,
        model="demo",
        timeout_seconds=5,
        temperature=0.2,
        max_output_tokens=1024,
    )

    plain = provider.payload([{"role": "user", "content": "你好"}], [], stream=False)
    streaming = provider.payload([{"role": "user", "content": "你好"}], [{"x": 1}], stream=True)

    assert plain["max_tokens"] == 1024
    assert streaming["max_tokens"] == 1024
    assert streaming["stream"] is True and streaming["tool_choice"] == "auto"


def test_token_estimate_counts_chinese_per_character() -> None:
    """估算口径：中文约一字一 token，英文约四字符一 token。只用于判断预算，不用于计费。"""
    assert providers.estimate_tokens("你好世界") >= 4
    assert providers.estimate_tokens("hello world hello world") < 10
    assert providers.estimate_tokens("") >= 1


def test_turn_budget_stops_the_loop_and_says_why(
    db_session: Session, actor, monkeypatch: pytest.MonkeyPatch
) -> None:
    """单轮预算用完就停：不是因为轮次上限，而是因为这一轮太贵——原因要说清楚。"""
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "assistant_turn_token_budget", 50, raising=False)
    scripted = ScriptedProvider(
        [_call("get_dashboard", '{"days": 14}', f"c{index}") for index in range(10)]
    )

    reply = _ask(db_session, actor, scripted, "把所有数据都给我看一遍")

    assert reply.truncated is True
    assert "token" in reply.reply and "上限" in reply.reply
    assert "把问题拆小" in reply.reply
    assert reply.tokens_used >= 50


def test_tool_call_fragments_are_assembled() -> None:
    """流式返回的工具调用是分片的，不攒起来就会拿到半个 JSON。

    半个 JSON 的后果很隐蔽：参数字典解析成空，工具以「没有参数」的方式静默跑错。
    """
    accumulator = providers.ToolCallAccumulator()
    accumulator.feed(
        [
            {
                "index": 0,
                "id": "call_1",
                "function": {"name": "get_dashboard", "arguments": '{"days"'},
            }
        ]
    )
    accumulator.feed([{"index": 0, "function": {"arguments": ": 7}"}}])

    calls = accumulator.result()

    assert len(calls) == 1
    assert calls[0].name == "get_dashboard"
    assert calls[0].arguments == '{"days": 7}'


def test_sse_parser_skips_noise_instead_of_crashing() -> None:
    """心跳、注释行、半截 JSON 一律跳过：一条坏块不该把整轮对话打断。"""
    lines = [
        "",
        ": ping",
        "data: not-json",
        'data: {"choices":[{"delta":{"content":"好"}}]}',
        "event: done",
        "data: [DONE]",
        'data: {"choices":[{"delta":{"content":"不该出现"}}]}',
    ]

    events = list(providers.iter_sse_data(lines))

    assert len(events) == 1
    assert events[0]["choices"][0]["delta"]["content"] == "好"


def test_stream_emits_events_in_order(db_session: Session, actor) -> None:
    """事件顺序：开聊 → 开始查 → 查完 → 逐段回答 → 结束（结束块里带完整结果）。"""
    scripted = ScriptedProvider(
        [
            _call("get_dashboard", '{"days": 7}'),
            providers.ProviderReply(text="最近 7 天食盐正常。"),
        ]
    )

    events = list(
        service.chat_stream(
            db_session,
            actor=actor,
            payload=ChatRequest(message="最近七天怎么样？"),
            provider=scripted,
        )
    )

    kinds = [event["type"] for event in events]
    assert kinds[0] == "start"
    assert kinds[1] == "tool_start"
    assert kinds[2] == "tool"
    assert "delta" in kinds
    assert kinds[-1] == "done"

    streamed = "".join(event["text"] for event in events if event["type"] == "delta")
    done = events[-1]["reply"]
    assert streamed == "最近 7 天食盐正常。"
    assert done["reply"] == streamed, "拼起来的片段必须与最终答案一致"
    assert done["conversation_id"]
    assert done["tool_calls"][0]["name"] == "get_dashboard"


def test_stream_endpoint_returns_event_stream(
    as_recorder: TestClient, install_provider: Callable[[ScriptedProvider], ScriptedProvider]
) -> None:
    install_provider(ScriptedProvider([providers.ProviderReply(text="今天午餐有 5 道菜。")]))

    response = as_recorder.post(f"{BASE}/chat/stream", json={"message": "今天吃什么？"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert '"type": "delta"' in response.text
    assert '"type": "done"' in response.text
    assert "今天午餐有 5 道菜。" in response.text

    # 流式这条路同样要落库：对话与消息都查得到
    conversations = as_recorder.get(f"{BASE}/conversations").json()
    assert conversations
    detail = as_recorder.get(f"{BASE}/conversations/{conversations[0]['id']}").json()
    assert [message["content"] for message in detail["messages"]] == [
        "今天吃什么？",
        "今天午餐有 5 道菜。",
    ]


def test_status_matches_whether_a_model_is_configured(as_recorder: TestClient) -> None:
    """状态接口说的必须与配置一致。

    这条用例**不能写死「未接模型」**：本地 .env 里配着演示用的模型端点，
    写死了在开发机上必挂，而在 CI 上又测不到「接了模型」那一半。
    """
    from app.core.config import get_settings

    settings = get_settings()
    configured = bool(settings.assistant_base_url and settings.assistant_model)
    body = as_recorder.get(f"{BASE}/status").json()

    assert body["enabled"] is configured
    assert len(body["tools"]) >= 8
    if configured:
        assert body["model"] and body["note"] is None
    else:
        assert "ASSISTANT_BASE_URL" in body["note"]


def test_build_provider_refuses_without_config() -> None:
    """没配模型时不给默认值硬撑：抛 503 并说清楚该配哪几个环境变量。"""
    from app.core.config import Settings
    from app.core.errors import ServiceUnavailableError

    blank = Settings(assistant_base_url=None, assistant_model=None)

    with pytest.raises(ServiceUnavailableError) as error:
        providers.build_provider(blank)

    assert "ASSISTANT_BASE_URL" in str(error.value)


def test_chat_endpoint_returns_conversation_and_proposals(
    as_recorder: TestClient, install_provider: Callable[[ScriptedProvider], ScriptedProvider]
) -> None:
    install_provider(
        ScriptedProvider(
            [
                _call(
                    "create_ingredient",
                    '{"name": "助手测试接口", "category": "OTHER", "data_source": "助手测试来源"}',
                ),
                providers.ProviderReply(text="请确认。"),
            ]
        )
    )

    response = as_recorder.post(f"{BASE}/chat", json={"message": "建一个食材"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["conversation_id"]
    assert body["proposals"][0]["status"] == "PENDING"
    assert body["proposals"][0]["status_label"] == "待确认"

    proposal_id = body["proposals"][0]["id"]
    confirmed = as_recorder.post(f"{BASE}/proposals/{proposal_id}/confirm")
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "CONFIRMED"
    assert confirmed.json()["result"]["名称"] == "助手测试接口"

    # 审计：这次对话与消息都查得到
    conversations = as_recorder.get(f"{BASE}/conversations").json()
    assert any(row["id"] == body["conversation_id"] for row in conversations)
    detail = as_recorder.get(f"{BASE}/conversations/{body['conversation_id']}").json()
    assert len(detail["messages"]) == 2
    assert detail["proposals"][0]["status"] == "CONFIRMED"


def test_proposal_can_be_cancelled_through_the_endpoint(
    as_recorder: TestClient, install_provider: Callable[[ScriptedProvider], ScriptedProvider]
) -> None:
    install_provider(
        ScriptedProvider(
            [
                _call(
                    "create_ingredient",
                    '{"name": "助手测试取消", "category": "OTHER", "data_source": "助手测试来源"}',
                ),
                providers.ProviderReply(text="请确认。"),
            ]
        )
    )
    created = as_recorder.post(f"{BASE}/chat", json={"message": "建一个食材"}).json()
    proposal_id = created["proposals"][0]["id"]

    cancelled = as_recorder.post(f"{BASE}/proposals/{proposal_id}/cancel")

    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"


def test_assistant_requires_login(client: TestClient) -> None:
    assert client.get(f"{BASE}/status").status_code == 401
    assert client.post(f"{BASE}/chat", json={"message": "你好"}).status_code == 401
    assert client.get(f"{BASE}/conversations").status_code == 401


def test_school_admin_can_ask_read_only_questions(
    as_school_admin: TestClient, install_provider: Callable[[ScriptedProvider], ScriptedProvider]
) -> None:
    install_provider(
        ScriptedProvider([providers.ProviderReply(text="最近 14 天食盐日均 2.2 克。")])
    )

    body = as_school_admin.post(f"{BASE}/chat", json={"message": "最近盐用超了吗？"}).json()

    assert body["reply"]
    assert body["tool_calls"] == []


def test_school_admin_can_read_all_conversations(
    as_recorder: TestClient,
    as_school_admin: TestClient,
    install_provider: Callable[[ScriptedProvider], ScriptedProvider],
) -> None:
    """学校管理方是只读观察者，但审计要看得到「助手都干了什么」。"""
    install_provider(ScriptedProvider([providers.ProviderReply(text="好")]))
    as_recorder.post(f"{BASE}/chat", json={"message": "审计用例：今天吃什么"})

    rows = as_school_admin.get(f"{BASE}/conversations").json()

    assert rows, "学校管理方应当能看到对话列表"


def test_destructive_tools_are_soft_delete_only(as_recorder: TestClient) -> None:
    """助手能做的最「狠」的事是停用（软删除），而且必须能撤回。

    物理删除在域层就不存在（食材/菜品都是软删），助手也够不到；
    这里把这条钉住：名字里带 deactivate 的工具都在，且都留下了撤回步骤的机制。
    """
    destructive = [tool for tool in tools.TOOLS if tool.name.startswith("deactivate_")]
    assert {tool.name for tool in destructive} == {"deactivate_ingredient", "deactivate_dish"}
    assert all(tool.execute is not None for tool in destructive)
    # 配套的「重新启用」必须存在，否则撤回无从谈起
    assert {"reactivate_ingredient", "reactivate_dish"} <= set(tools.TOOLS_BY_NAME)

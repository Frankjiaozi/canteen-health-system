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
from app.modules.dish import service as dish_service
from app.modules.dish.models import Dish
from app.modules.ingredient.models import Ingredient
from app.modules.nutrition.models import DishNutrition
from app.shared.enums import AssistantProposalStatus, AuditAction
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
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

import asyncio
import json
from contextlib import ExitStack
from copy import deepcopy
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from test_agent import DISHES, TODAY, BusinessFake, events, new_session, send

from zhiwei_agent.config import Settings
from zhiwei_agent.errors import AgentError
from zhiwei_agent.main import create_app
from zhiwei_agent.model import complete
from zhiwei_agent.schemas import PlanParameters
from zhiwei_agent.smoke import check_model
from zhiwei_agent.tools import Tools


def tool(name, arguments=None):
    return {
        "role": "assistant",
        "tool_calls": [
            {
                "id": str(uuid4()),
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments or {})},
            }
        ],
    }


def settings(tmp_path):
    return Settings(
        mode="model",
        model_base_url="https://model.invalid/v1",
        model_name="test",
        model_api_key="private-test-key",
        data_path=tmp_path / "model.sqlite3",
        _env_file=None,
    )


@pytest.fixture
def model_client(tmp_path, monkeypatch):
    with ExitStack() as stack:

        def setup(responses, handler=None):
            business = BusinessFake()
            history = []
            replies = iter(responses)

            async def fake(settings, messages):
                history.append(deepcopy(messages))
                response = next(replies)
                if isinstance(response, Exception):
                    raise response
                return response

            monkeypatch.setattr("zhiwei_agent.model.complete", fake)
            app = create_app(settings(tmp_path), httpx.MockTransport(handler or business))
            client = stack.enter_context(TestClient(app))
            client.cookies.set("canteen_token", "owner")
            return client, business, app, history

        yield setup


def test_user_explicit_parameters_override_model_disagreement(model_client):
    client, business, _, _ = model_client(
        [
            tool("generate_menu_plan", {"diner_count": 1200, "budget_per_person": "12"}),
            {"content": "方案已生成。"},
        ]
    )
    result = events(send(client, new_session(client), "安排明天午餐1000人，每人预算9元"))[-1][
        "conversation"
    ]
    parameters = result["plans"][0]["parameters"]
    assert parameters["diner_count"] == 1000 and parameters["budget_per_person"] == "9"
    assert len([row for row in business.calls if row.url.path.endswith("/generate")]) == 1


def test_generated_answer_does_not_repeat_model_invented_numbers_or_caliber(model_client):
    client, _, _, _ = model_client(
        [
            tool("generate_menu_plan"),
            {"content": "单份口径能量99999千卡；预算占用率36%；营养全部达标。"},
        ]
    )
    result = events(send(client, new_session(client)))[-1]["conversation"]
    content = result["messages"][-1]["content"]
    assert "99999" not in content and "预算占用率36%" not in content
    assert "不能把求解成功表述为营养全部达标" in content
    assert "整餐人均营养供给" in content
    assert result["plans"][-1]["result"]["total_cost"] in content


def test_model_can_check_data_when_user_explicitly_forbids_generation(model_client):
    client, business, _, history = model_client(
        [
            tool("check_data_readiness"),
            {"content": "已检查数据，请查看缺项。"},
        ]
    )
    result = events(send(client, new_session(client), "检查数据，列出缺项，不要生成菜单"))[-1][
        "conversation"
    ]
    assert result["readiness"] and not result["plans"]
    assert len(history) == 2
    assert not any(row.url.path.endswith("/generate") for row in business.calls)


def test_model_cannot_generate_when_user_requested_readonly_inspection(model_client):
    client, business, _, history = model_client(
        [
            tool("generate_menu_plan"),
            tool("check_data_readiness"),
            {"content": "已按只读要求检查。"},
        ]
    )
    result = events(send(client, new_session(client), "请检查数据，不要生成菜单"))[-1][
        "conversation"
    ]
    assert json.loads(history[1][-1]["content"])["code"] == "generation_not_requested"
    assert result["readiness"] and not result["plans"]
    assert not any(row.url.path.endswith("/generate") for row in business.calls)


def test_model_cannot_silently_change_an_unmentioned_condition(model_client):
    client, business, _, _ = model_client([tool("generate_menu_plan", {"meal_type": "DINNER"})])
    result = events(send(client, new_session(client), "安排明天菜单"))[-1]["conversation"]
    assert not result["plans"]
    assert result["pending_task"]["field"] == "meal_type"
    assert result["pending_task"]["parameters"]["meal_type"] == "LUNCH"
    assert not any(row.url.path.endswith("/generate") for row in business.calls)


def test_clarification_cannot_persist_model_invented_known_parameters(model_client):
    client, business, _, _ = model_client(
        [
            tool(
                "clarify_task",
                {
                    "question": "还要排除哪些菜？",
                    "field": "excluded_dish_ids",
                    "known_parameters": {"diner_count": 10000},
                },
            ),
        ]
    )
    result = events(send(client, new_session(client), "安排明天午餐"))[-1]["conversation"]
    assert result["pending_task"]["field"] == "diner_count"
    assert result["pending_task"]["parameters"]["diner_count"] == 800
    assert not result["plans"]
    assert all(row.url.path.endswith("auth/me") for row in business.calls)


def test_business_timeout_ends_stream_and_releases_session(model_client):
    business = BusinessFake()

    def handler(request):
        if request.url.path.endswith("/generate"):
            raise httpx.ReadTimeout("private transport debug", request=request)
        return business(request)

    client, _, app, _ = model_client([tool("generate_menu_plan")], handler)
    sid = new_session(client)
    result = events(send(client, sid))
    assert result[-2]["code"] == "business_timeout"
    assert result[-1]["type"] == "done" and not result[-1]["conversation"]["plans"]
    assert result[-1]["conversation"]["messages"][-1]["trace"][-1]["status"] == "error"
    app.state.store.acquire(sid, "owner")
    app.state.store.release(sid, "owner")


def test_invalid_tool_arguments_can_be_corrected_without_duplicate_generation(model_client):
    invalid = tool("generate_menu_plan")
    invalid["tool_calls"][0]["function"]["arguments"] = "[1,2]"
    client, business, _, history = model_client(
        [
            invalid,
            tool("generate_menu_plan"),
            {"content": "已返回待确认方案。"},
        ]
    )
    result = events(send(client, new_session(client)))[-1]["conversation"]
    assert len(result["plans"]) == 1
    assert [row["status"] for row in result["messages"][-1]["trace"]] == ["error", "success"]
    assert json.loads(history[1][-1]["content"])["code"] == "invalid_tool_arguments"
    assert len([row for row in business.calls if row.url.path.endswith("/generate")]) == 1


def test_unknown_tool_has_a_readable_error_and_never_reaches_business(model_client):
    client, business, _, history = model_client(
        [tool("execute_sql"), {"content": "该工具不开放。"}]
    )
    result = events(send(client, new_session(client)))[-1]["conversation"]
    assert json.loads(history[1][-1]["content"])["code"] == "unknown_tool"
    assert result["messages"][-1]["trace"][0]["status"] == "error"
    assert all(row.url.path.endswith("auth/me") for row in business.calls)


def test_ambiguous_reference_asks_using_real_candidates_without_generating(model_client):
    client, business, _, _ = model_client(
        [
            tool("generate_menu_plan"),
            {"content": "已返回方案。"},
            tool("generate_menu_plan", {"excluded_dish_ids": [str(uuid4())]}),
        ]
    )
    sid = new_session(client)
    events(send(client, sid))
    before = len(business.calls)
    result = events(send(client, sid, "不要这个菜", revision=1))[-1]["conversation"]
    assert len(result["plans"]) == 1
    assert result["messages"][-1]["kind"] == "clarification"
    assert result["messages"][-1]["suggestions"]
    names = {row["name"] for row in DISHES}
    assert all(row["label"] in names for row in result["messages"][-1]["suggestions"])
    assert not any(row.url.path.endswith("/generate") for row in business.calls[before:])


def test_unexpected_failure_is_sanitized_and_idempotent(model_client, caplog):
    client, _, _, history = model_client([RuntimeError("private-test-key internal provider debug")])
    sid, rid = new_session(client), str(uuid4())
    first = send(client, sid, request_id=rid)
    result = events(first)
    assert result[-2]["code"] == "internal_error"
    assert result[-1]["conversation"]["messages"][-1]["kind"] == "failure"
    assert "private-test-key" not in first.text + caplog.text
    replay = events(send(client, sid, request_id=rid))
    assert len(replay) == 1 and len(history) == 1


def test_repeated_empty_model_responses_end_as_a_recoverable_failure(model_client):
    client, _, _, history = model_client([{"content": ""}] * 5)
    result = events(send(client, new_session(client)))
    assert result[-2]["code"] == "model_empty_response"
    assert result[-1]["conversation"]["messages"][-1]["kind"] == "failure"
    assert len(history) == 5


def test_tool_limit_retains_completed_calculation(model_client):
    client, business, _, _ = model_client(
        [
            tool("generate_menu_plan"),
            *[tool("get_current_plan") for _ in range(4)],
        ]
    )
    result = events(send(client, new_session(client)))
    assert result[-2]["code"] == "tool_limit"
    assert len(result[-1]["conversation"]["plans"]) == 1
    assert len([row for row in business.calls if row.url.path.endswith("/generate")]) == 1


@pytest.mark.parametrize(
    "message",
    [
        {"content": []},
        {"tool_calls": {}},
        {"tool_calls": [None]},
        {"tool_calls": [{"id": "a", "function": {"name": "list_dishes", "arguments": {}}}]},
        {"tool_calls": [{"function": {"name": "list_dishes", "arguments": "{}"}}]},
        {
            "tool_calls": [
                {"id": "a", "type": "sql", "function": {"name": "list_dishes", "arguments": "{}"}}
            ]
        },
    ],
)
def test_malformed_model_envelopes_are_rejected_without_exposing_provider_data(tmp_path, message):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"choices": [{"message": message}]})
    )
    with pytest.raises(AgentError) as caught:
        asyncio.run(complete(settings(tmp_path), [], transport))
    assert caught.value.code == "invalid_model_response"
    assert "private-test-key" not in str(caught.value)


def test_model_timeout_is_distinct_from_invalid_tool_arguments(tmp_path):
    def timeout(request):
        raise httpx.ReadTimeout("private-test-key", request=request)

    with pytest.raises(AgentError) as caught:
        asyncio.run(complete(settings(tmp_path), [], httpx.MockTransport(timeout)))
    assert caught.value.code == "model_timeout" and caught.value.status == 503
    assert "private-test-key" not in str(caught.value)


def test_manual_smoke_checks_protocol_without_executing_business(tmp_path):
    calls = []

    def provider(request):
        calls.append(request)
        return httpx.Response(200, json={"choices": [{"message": tool("list_dishes")}]})

    result = asyncio.run(check_model(settings(tmp_path), httpx.MockTransport(provider)))
    assert result == {"status": "ok", "check": "model_tool_protocol", "business_executed": False}
    assert len(calls) == 1 and "cookie" not in calls[0].headers


def test_unconfigured_smoke_does_not_make_a_request(tmp_path):
    with pytest.raises(AgentError) as caught:
        asyncio.run(
            check_model(
                Settings(mode="rules", data_path=tmp_path / "state.sqlite3", _env_file=None)
            )
        )
    assert caught.value.code == "model_not_configured"


def test_unknown_excluded_uuid_is_verified_against_the_business_api(tmp_path):
    unknown = str(uuid4())

    class Business:
        def __init__(self):
            self.paths = []

        async def request(self, method, path, **kwargs):
            self.paths.append(path)
            if path == "dishes":
                return {"items": DISHES, "total": len(DISHES)}
            if path == f"dishes/{unknown}":
                raise AgentError("菜品不存在", 404, "not_found")
            raise AssertionError(path)

    from zhiwei_agent.store import Store

    business = Business()
    conversation = Store(tmp_path / "unknown.sqlite3").create("owner")
    tools = Tools(business, conversation, "RECORDER", PlanParameters(on_date=TODAY))
    with pytest.raises(AgentError) as caught:
        asyncio.run(tools.execute("generate_menu_plan", {"excluded_dish_ids": [unknown]}))
    assert caught.value.code == "not_found"
    assert business.paths == ["dishes", f"dishes/{unknown}"]

"""Agent 任务书回归：HTTP 边界、版本、快照与失败恢复。"""

import asyncio
import json
from copy import deepcopy
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from test_agent import TODAY, BusinessFake, events, new_session, send
from test_agent import context as context

from zhiwei_agent.business import BusinessClient
from zhiwei_agent.config import Settings
from zhiwei_agent.errors import AgentError
from zhiwei_agent.main import create_app
from zhiwei_agent.runner import run
from zhiwei_agent.schemas import MessageRequest


@pytest.mark.parametrize("prediction", [None, 0, 920])
def test_forecast_keeps_empty_intervals_and_zero_distinct(tmp_path, prediction):
    business = BusinessFake()

    def handler(request):
        response = business(request)
        if request.url.path.endswith("forecast/diner-count"):
            body = response.json()
            body.update(predicted_diner_count=prediction, lower=None, upper=None, samples=[])
            return httpx.Response(200, json=body)
        return response

    cfg = Settings(mode="rules", data_path=tmp_path / "forecast.sqlite3", _env_file=None)
    with TestClient(create_app(cfg, httpx.MockTransport(handler))) as client:
        client.cookies.set("canteen_token", "owner")
        response = client.get(
            "/agent-api/v1/diner-forecast", params={"on_date": str(TODAY), "meal_type": "LUNCH"}
        )
        assert response.status_code == 200
        assert response.json()["predicted_diner_count"] == prediction
        assert response.json()["lower"] is None and response.json()["upper"] is None


def test_malformed_forecast_is_a_contract_error_instead_of_a_server_crash(tmp_path):
    business = BusinessFake()

    def handler(request):
        if request.url.path.endswith("forecast/diner-count"):
            return httpx.Response(200, json={"predicted_diner_count": "private provider debug"})
        return business(request)

    cfg = Settings(mode="rules", data_path=tmp_path / "malformed.sqlite3", _env_file=None)
    with TestClient(create_app(cfg, httpx.MockTransport(handler))) as client:
        client.cookies.set("canteen_token", "owner")
        response = client.get("/agent-api/v1/diner-forecast", params={"on_date": str(TODAY)})
        assert response.status_code == 502 and response.json()["code"] == "contract_mismatch"
        assert "private provider debug" not in response.text


def test_multiple_turns_keep_unchanged_conditions_and_sessions_stay_isolated(context):
    client, _, _ = context
    sid = new_session(client)
    first = events(send(client, sid, "安排明天午餐1000人，每人预算8元"))[-1]["conversation"]

    def follow(text, previous):
        return events(
            client.post(
                f"/agent-api/v1/sessions/{sid}/messages",
                json={
                    "content": text,
                    "parameters": previous["plans"][-1]["parameters"],
                    "expected_revision": len(previous["plans"]),
                    "request_id": str(uuid4()),
                },
            )
        )[-1]["conversation"]

    second = follow("预算改为9元，其余不变", first)
    target = second["plans"][-1]["result"]["dishes"][0]
    third = follow(f"去掉{target['dish_name']}，其余不变", second)
    params = third["plans"][-1]["parameters"]
    assert params["diner_count"] == 1000 and params["budget_per_person"] == "9"
    assert (
        params["meal_type"] == "LUNCH"
        and params["on_date"] == first["plans"][0]["parameters"]["on_date"]
    )
    assert params["excluded_dish_ids"] == [target["dish_id"]]
    other = client.get(f"/agent-api/v1/sessions/{new_session(client)}").json()
    assert other["plans"] == [] and other["pending_task"] is None


@pytest.mark.parametrize("action", ["publish", "undo"])
def test_session_lock_also_protects_publish_and_undo(context, action):
    client, business, app = context
    sid = new_session(client)
    events(send(client, sid))
    app.state.store.acquire(sid, "owner")
    before = len(business.calls)
    try:
        result = client.post(f"/agent-api/v1/sessions/{sid}/{action}", json={"revision": 1})
        assert result.status_code == 409 and result.json()["code"] == "session_busy"
        assert all(row.url.path.endswith("auth/me") for row in business.calls[before:])
    finally:
        app.state.store.release(sid, "owner")


def test_review_markdown_uses_saved_notice_not_current_configuration(context):
    client, _, app = context
    sid = new_session(client)
    events(send(client, sid, "核查最近7天供应记录"))
    saved = app.state.store.get(sid, "owner")
    saved.review.data_notice = "核查当时的合成数据说明"
    app.state.store.save(saved, "owner")
    report = client.get(f"/agent-api/v1/sessions/{sid}/review.md")
    assert report.status_code == 200 and "核查当时的合成数据说明" in report.text


def test_forecast_has_an_explicit_nullable_openapi_contract(context):
    client, _, _ = context
    spec = client.get("/agent-api/openapi.json").json()
    schema = spec["paths"]["/agent-api/v1/diner-forecast"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    assert schema["$ref"].endswith("/DinerForecast")
    fields = spec["components"]["schemas"]["DinerForecast"]["properties"]
    for field in ("predicted_diner_count", "lower", "upper"):
        assert {"type": "null"} in fields[field]["anyOf"]


def test_readonly_data_check_with_no_generation_is_not_cancelled(context):
    client, business, _ = context
    business.readiness_state = "blocked"
    result = events(
        send(client, new_session(client), "请检查数据准备情况，列出缺项，不要生成菜单")
    )[-1]["conversation"]
    assert result["readiness"] and result["readiness"]["state"] == "blocked"
    assert not result["plans"] and result["pending_task"] is None
    assert any(row.url.path.endswith("menu-plan/readiness") for row in business.calls)
    assert not any(row.url.path.endswith("/generate") for row in business.calls)


@pytest.mark.parametrize(
    "body, expected, code",
    [
        ({"detail": "该角色不能修改菜单"}, "该角色不能修改菜单", "business_error"),
        (
            {"detail": [{"loc": ["body", "budget"], "msg": "必须大于零"}]},
            "业务请求参数有误，请核对字段",
            "business_error",
        ),
        (["invalid envelope"], "业务操作失败，请重试", "business_error"),
    ],
)
def test_business_error_envelopes_remain_readable(body, expected, code):
    async def scenario():
        business = BusinessClient(
            "http://business/api/v1",
            "canteen_token",
            "secret",
            httpx.MockTransport(lambda request: httpx.Response(422, json=body)),
        )
        try:
            with pytest.raises(AgentError) as caught:
                await business.request("POST", "menu-plan/generate")
            assert caught.value.message == expected
            assert caught.value.code == code
        finally:
            await business.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "path",
    [
        "https://other.invalid/api",
        "//other.invalid",
        "../auth/me",
        "dishes?token=secret",
        "dishes#fragment",
    ],
)
def test_business_client_rejects_paths_outside_fixed_api(path):
    calls = []

    async def scenario():
        business = BusinessClient(
            "http://business/api/v1",
            "canteen_token",
            "secret",
            httpx.MockTransport(
                lambda request: calls.append(request) or httpx.Response(200, json={})
            ),
        )
        try:
            with pytest.raises(AgentError, match="业务接口路径"):
                await business.request("GET", path)
        finally:
            await business.close()

    asyncio.run(scenario())
    assert calls == []


def test_undo_checks_the_version_requested_by_the_caller(context):
    client, business, _ = context
    sid = new_session(client)
    events(send(client, sid))
    client.post(f"/agent-api/v1/sessions/{sid}/publish", json={"revision": 1})
    before = len(business.calls)
    conflict = client.post(f"/agent-api/v1/sessions/{sid}/undo", json={"revision": 2})
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "revision_conflict"
    assert not any(row.url.path.endswith("/undo") for row in business.calls[before:])
    assert (
        client.post(f"/agent-api/v1/sessions/{sid}/undo", json={"revision": 1}).status_code == 200
    )


def test_undone_version_cannot_be_republished_and_all_exports_say_undone(context):
    client, business, _ = context
    sid = new_session(client)
    events(send(client, sid))
    client.post(f"/agent-api/v1/sessions/{sid}/publish", json={"revision": 1})
    client.post(f"/agent-api/v1/sessions/{sid}/undo")
    before = len(business.calls)
    assert "已撤回" in client.get(f"/agent-api/v1/sessions/{sid}/purchase.csv").text
    report = client.get(f"/agent-api/v1/sessions/{sid}/report.html").text
    assert "已撤回" in report and "撤回人" in report
    summary = events(send(client, sid, "解释当前方案依据", revision=1))[-1]["conversation"]
    assert "已撤回" in summary["messages"][-1]["content"]
    retry = client.post(f"/agent-api/v1/sessions/{sid}/publish", json={"revision": 1})
    assert retry.status_code == 409
    assert not any(row.url.path.endswith("/publish") for row in business.calls[before:])


def test_zero_cost_snapshot_is_not_reported_as_missing(context):
    client, _, app = context
    sid = new_session(client)
    events(send(client, sid))
    saved = app.state.store.get(sid, "owner")
    saved.plans[0].result["total_cost"] = 0
    app.state.store.save(saved, "owner")
    assert "金额不完整" not in client.get(f"/agent-api/v1/sessions/{sid}/purchase.csv").text


def test_interrupted_stream_is_saved_and_same_request_does_not_run_twice(context):
    _, business_fake, app = context
    store = app.state.store
    conversation = store.create("owner")
    request = MessageRequest(
        content="安排菜单",
        parameters={"on_date": TODAY, "diner_count": 800},
        request_id=uuid4(),
        expected_revision=0,
    )

    async def scenario():
        business = BusinessClient(
            "http://business/api/v1", "canteen_token", "owner", httpx.MockTransport(business_fake)
        )
        stream = run(
            store,
            conversation,
            "owner",
            "RECORDER",
            business,
            Settings(mode="rules", data_path=store.path, _env_file=None),
            request,
        )
        store.acquire(conversation.id, "owner")
        try:
            assert json.loads(await anext(stream))["type"] == "status"
            await stream.aclose()
        finally:
            await business.close()

    asyncio.run(scenario())
    saved = store.get(conversation.id, "owner")
    assert str(request.request_id) in saved.completed_requests
    assert saved.messages[-1].kind == "failure"
    assert "中断" in saved.messages[-1].content
    store.acquire(conversation.id, "owner")
    store.release(conversation.id, "owner")


def test_undo_payload_schema_keeps_legacy_no_body_support(context):
    client, _, _ = context
    route = client.get("/agent-api/openapi.json").json()["paths"][
        "/agent-api/v1/sessions/{session_id}/undo"
    ]["post"]
    assert not route["requestBody"].get("required", False)


def test_readonly_account_cannot_undo_or_access_other_exports(context):
    client, _, _ = context
    sid = new_session(client)
    events(send(client, sid))
    client.cookies.set("canteen_token", "other")
    for suffix in ("purchase.csv", "report.html", "review.md"):
        assert client.get(f"/agent-api/v1/sessions/{sid}/{suffix}").status_code == 404
    client.cookies.set("canteen_token", "school")
    assert (
        client.post(f"/agent-api/v1/sessions/{sid}/undo", json={"revision": 1}).status_code == 403
    )


def test_old_snapshot_exports_never_trigger_new_business_computation(context):
    client, business, app = context
    sid = new_session(client)
    events(send(client, sid))
    first = deepcopy(app.state.store.get(sid, "owner").plans[0].result)
    events(send(client, sid, "改成1000人安排菜单", revision=1))
    before = len(business.calls)
    csv = client.get(f"/agent-api/v1/sessions/{sid}/purchase.csv?revision=1")
    html = client.get(f"/agent-api/v1/sessions/{sid}/report.html?revision=1")
    assert first["total_cost"] in csv.text and first["total_cost"] in html.text
    assert all(row.url.path.endswith("auth/me") for row in business.calls[before:])

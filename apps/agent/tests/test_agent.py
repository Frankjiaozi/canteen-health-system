import json
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi.testclient import TestClient

from zhiwei_agent.config import Settings
from zhiwei_agent.errors import AgentError
from zhiwei_agent.main import create_app
from zhiwei_agent.rules import parameters_from_text
from zhiwei_agent.schemas import PlanParameters

TODAY = datetime.now(ZoneInfo("Asia/Shanghai")).date()
PLAN = json.loads((Path(__file__).parent / "fixtures/menu_plan.json").read_text(encoding="utf-8"))
DISHES = [
    {"id": row["dish_id"], "name": row["dish_name"], "category_label": row["category_label"]}
    for row in PLAN["dishes"]
]


class BusinessFake:
    def __init__(self):
        self.calls = []
        self.generate_status = 200
        self.readiness_state = "ready"

    def __call__(self, request: httpx.Request):
        self.calls.append(request)
        token = request.headers.get("cookie", "")
        if "expired" in token:
            return httpx.Response(401, json={"code": "unauthorized", "message": "登录已过期"})
        if request.url.path.endswith("auth/me"):
            return httpx.Response(
                200,
                json={
                    "id": "other" if "other" in token else "owner",
                    "display_name": "演示用户",
                    "role": "SCHOOL_ADMIN" if "school" in token else "RECORDER",
                },
            )
        if request.url.path.endswith("dishes"):
            return httpx.Response(200, json={"items": DISHES, "total": len(DISHES)})
        if request.url.path.endswith("forecast/diner-count"):
            return httpx.Response(
                200,
                json={
                    "on_date": request.url.params["on_date"],
                    "meal_type": request.url.params["meal_type"],
                    "meal_type_label": "午餐",
                    "predicted_diner_count": 920,
                    "lower": 840,
                    "upper": 1030,
                    "basis": "SAME_WEEKDAY",
                    "basis_label": "同星期几中位数",
                    "samples": [],
                    "calendar_note": None,
                    "note": "预测值说明",
                },
            )
        if request.url.path.endswith("menu-plan/readiness"):
            return httpx.Response(
                200,
                json={
                    "state": self.readiness_state,
                    "on_date": request.url.params["on_date"],
                    "meal_type": request.url.params["meal_type"],
                    "meal_type_label": "午餐",
                    "available_count": 10,
                    "predicted_count": 10,
                    "history_record_count": 56,
                    "issue_count": 1 if self.readiness_state == "blocked" else 0,
                    "issues": [{"severity": "blocking", "title": "缺少主食"}]
                    if self.readiness_state == "blocked"
                    else [],
                },
            )
        if request.url.path.endswith("menu-plan/generate"):
            if self.generate_status != 200:
                return httpx.Response(
                    self.generate_status,
                    json={
                        "code": "business_rule_violated",
                        "message": "候选菜品不足",
                        "details": {"conflicts": ["食材种类不足"]},
                    },
                )
            result = {
                **PLAN,
                "date": request.url.params["on_date"],
                "diner_count": int(request.url.params.get("diner_count", 800)),
            }
            return httpx.Response(200, json=result)
        if request.url.path.endswith("/publish"):
            return httpx.Response(
                200,
                json={
                    "menu_day_id": "demo-menu",
                    "published_at": "2026-10-16T12:00:00+08:00",
                    "published_by": "演示用户",
                    "already_published": False,
                },
            )
        if request.url.path.endswith("/undo"):
            return httpx.Response(
                200,
                json={
                    "suggestion_id": "demo-suggestion",
                    "on_date": str(TODAY + timedelta(days=1)),
                    "meal_type": "LUNCH",
                    "meal_type_label": "午餐",
                    "undone_at": "2026-10-16T12:30:00+08:00",
                    "undone_by": "演示用户",
                },
            )
        if request.url.path.endswith("collection/logs"):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "date": str(TODAY),
                            "meal_type": "LUNCH",
                            "meal_type_label": "午餐",
                            "diner_count": 100,
                            "salt_total_g": "300",
                            "waste_ratio": "0.2",
                            "anomaly_flags": [{"label": "用量对不上", "system": True}],
                        }
                    ],
                    "total": 1,
                },
            )
        raise AssertionError(f"Unexpected business path {request.url.path}")


@pytest.fixture
def context(tmp_path):
    business = BusinessFake()
    settings = Settings(data_path=tmp_path / "state.sqlite3", mode="rules", _env_file=None)
    app = create_app(settings, business_transport=httpx.MockTransport(business))
    with TestClient(app) as client:
        client.cookies.set("canteen_token", "owner")
        yield client, business, app


def new_session(client):
    response = client.post("/agent-api/v1/sessions")
    assert response.status_code == 201
    return response.json()["id"]


def send(client, session_id, text="安排明天午餐800人，每人预算8元", revision=0, request_id=None):
    return client.post(
        f"/agent-api/v1/sessions/{session_id}/messages",
        json={
            "content": text,
            "parameters": {
                "on_date": str(TODAY + timedelta(days=1)),
                "diner_count": 800,
                "budget_per_person": "8",
            },
            "expected_revision": revision,
            "request_id": request_id or str(uuid4()),
        },
    )


def events(response):
    assert response.status_code == 200, response.text
    return [json.loads(line) for line in response.text.splitlines() if line]


def test_rules_generate_real_tool_then_publish_and_download(context):
    client, business, app = context
    sid = new_session(client)
    stream = events(send(client, sid))
    result = stream[-1]["conversation"]
    assert stream[0]["type"] == "status"
    assert result["plans"][0]["revision"] == 1
    assert result["plans"][0]["result"]["total_cost"] == PLAN["total_cost"]
    assert result["messages"][-1]["trace"][0]["status"] == "success"
    assert not any(call.url.path.endswith("/publish") for call in business.calls)
    published = client.post(f"/agent-api/v1/sessions/{sid}/publish", json={"revision": 1})
    assert published.status_code == 200
    assert published.json()["plans"][0]["publication"]["menu_day_id"] == "demo-menu"
    csv = client.get(f"/agent-api/v1/sessions/{sid}/purchase.csv")
    assert csv.status_code == 200 and csv.content.startswith(b"\xef\xbb\xbf")
    assert "已确认发布" in csv.text
    saved = app.state.store.get(sid, "owner")
    assert saved.plans[0].result["snapshot_token"] == PLAN["snapshot_token"]


def test_publish_then_undo_marks_the_version_and_refuses_a_second_time(context):
    """发布之后可以撤回；撤回走的是业务接口，回执记在版本上，且只能撤一次。"""
    client, business, _ = context
    sid = new_session(client)
    events(send(client, sid))
    published = client.post(f"/agent-api/v1/sessions/{sid}/publish", json={"revision": 1})
    assert published.status_code == 200
    assert published.json()["plans"][0]["undone"] is None

    undone = client.post(f"/agent-api/v1/sessions/{sid}/undo")

    assert undone.status_code == 200, undone.text
    body = undone.json()["plans"][0]
    # 发布回执保留不动，撤回是另一条记录——「发布过」和「还生效」不能混成一个字段
    assert body["publication"]["menu_day_id"] == "demo-menu"
    assert body["undone"]["undone_by"] == "演示用户"
    assert any(call.url.path.endswith("/undo") for call in business.calls)
    assert client.post(f"/agent-api/v1/sessions/{sid}/undo").status_code == 409


def test_owner_and_expired_cookie_are_enforced_on_every_request(context):
    client, _, _ = context
    sid = new_session(client)
    client.cookies.set("canteen_token", "other")
    assert client.get(f"/agent-api/v1/sessions/{sid}").status_code == 404
    assert client.get(f"/agent-api/v1/sessions/{sid}/purchase.csv").status_code == 404
    client.cookies.set("canteen_token", "expired")
    assert client.get("/agent-api/v1/status").status_code == 401
    client.cookies.clear()
    assert client.get("/agent-api/v1/sessions").status_code == 401


def test_diner_forecast_proxy_returns_the_business_prediction(context):
    client, business, _ = context
    response = client.get(
        "/agent-api/v1/diner-forecast",
        params={"on_date": str(TODAY), "meal_type": "LUNCH"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["predicted_diner_count"] == 920
    assert any(call.url.path.endswith("forecast/diner-count") for call in business.calls)


def test_revision_conflict_busy_and_idempotent_retry(context):
    client, business, app = context
    sid, rid = new_session(client), str(uuid4())
    events(send(client, sid, request_id=rid))
    count = len([call for call in business.calls if call.url.path.endswith("/generate")])
    retry = events(send(client, sid, request_id=rid))
    assert len(retry) == 1
    assert len([call for call in business.calls if call.url.path.endswith("/generate")]) == count
    assert send(client, sid, text="核查最近7天", request_id=rid).status_code == 409
    assert send(client, sid, revision=0).status_code == 409
    assert (
        client.post(f"/agent-api/v1/sessions/{sid}/publish", json={"revision": 2}).status_code
        == 409
    )
    app.state.store.acquire(sid, "owner")
    assert send(client, sid, revision=1).status_code == 409
    app.state.store.release(sid, "owner")


def test_business_error_retains_trace_and_session_is_usable(context):
    client, business, _ = context
    sid = new_session(client)
    business.generate_status = 422
    result = events(send(client, sid))
    assert any(item["type"] == "error" for item in result)
    assert result[-1]["conversation"]["plans"] == []
    assert result[-1]["conversation"]["messages"][-1]["trace"][-1]["status"] == "error"
    business.generate_status = 200
    assert events(send(client, sid))[-1]["conversation"]["plans"]


def test_school_role_can_review_but_not_generate_or_publish(context):
    client, _, _ = context
    client.cookies.set("canteen_token", "school")
    assert not client.get("/agent-api/v1/status").json()["can_plan"]
    sid = new_session(client)
    review = events(send(client, sid, "核查最近7天供应记录"))[-1]["conversation"]["review"]
    assert review["record_count"] == 1
    assert len(review["issues"]) == 2
    assert len(review["missing_dates"]) == 6
    assert client.get(f"/agent-api/v1/sessions/{sid}/review.md").status_code == 200
    assert any(row["type"] == "error" for row in events(send(client, sid)))
    assert (
        client.post(f"/agent-api/v1/sessions/{sid}/publish", json={"revision": 1}).status_code
        == 403
    )
    assert client.post(f"/agent-api/v1/sessions/{sid}/undo").status_code == 403


def test_invalid_constraints_and_cross_site_requests_rejected(context):
    client, _, _ = context
    assert (
        client.post(
            "/agent-api/v1/sessions", headers={"Origin": "https://attacker.invalid"}
        ).status_code
        == 403
    )
    sid = new_session(client)
    payload = {
        "content": "安排菜单",
        "parameters": {"on_date": str(TODAY), "diner_count": -1},
        "request_id": str(uuid4()),
        "expected_revision": 0,
    }
    assert client.post(f"/agent-api/v1/sessions/{sid}/messages", json=payload).status_code == 422


def test_rules_preserve_constraints_and_resolve_names():
    base = PlanParameters(
        on_date=TODAY, diner_count=800, budget_per_person="8", excluded_dish_ids=[DISHES[0]["id"]]
    )
    changed = parameters_from_text(
        f"明天换掉{DISHES[1]['name']}，改成1000人，预算每人7元", base, DISHES
    )
    assert changed.diner_count == 1000 and str(changed.budget_per_person) == "7"
    assert len(changed.excluded_dish_ids) == 2
    assert not parameters_from_text("清空排除", changed, DISHES).excluded_dish_ids
    with pytest.raises(Exception, match="完整菜名"):
        parameters_from_text("换掉那道菜", base, DISHES)


def test_rules_parse_changed_values_without_silently_using_old_ones():
    base = PlanParameters(on_date=TODAY, diner_count=800, budget_per_person="8")
    changed = parameters_from_text("从800人改成1000人，预算从8元改成9元，下周三午餐", base, DISHES)
    assert changed.diner_count == 1000 and changed.budget_per_person == 9
    assert changed.on_date == TODAY + timedelta(days=7 - TODAY.weekday() + 2)
    for content in (
        "安排800.5人午餐",
        "安排-800人午餐",
        "明天和后天安排菜单",
        "预算降低一点",
        "安排下周菜单",
    ):
        with pytest.raises(AgentError):
            parameters_from_text(content, base, DISHES)


def test_name_matching_does_not_exclude_shorter_name_inside_long_name():
    a, b = str(uuid4()), str(uuid4())
    dishes = [{"id": a, "name": "米饭"}, {"id": b, "name": "杂粮米饭"}]
    base = PlanParameters(on_date=TODAY)
    result = parameters_from_text("换掉杂粮米饭", base, dishes)
    assert [str(item) for item in result.excluded_dish_ids] == [b]


def test_rules_do_not_exclude_dishes_explicitly_kept():
    a, b = str(uuid4()), str(uuid4())
    dishes = [{"id": a, "name": "番茄炒蛋"}, {"id": b, "name": "清炒青菜"}]
    base = PlanParameters(on_date=TODAY)
    result = parameters_from_text("换掉番茄炒蛋，清炒青菜保留，其余条件不变", base, dishes)
    assert [str(item) for item in result.excluded_dish_ids] == [a]
    result = parameters_from_text("换掉番茄炒蛋但清炒青菜保留", base, dishes)
    assert [str(item) for item in result.excluded_dish_ids] == [a]
    kept = parameters_from_text(
        "不要排除清炒青菜", PlanParameters(on_date=TODAY, excluded_dish_ids=[b]), dishes
    )
    assert kept.excluded_dish_ids == []


def test_data_check_and_blocked_generation_use_real_readiness_tool(context):
    client, business, _ = context
    sid = new_session(client)
    check = events(send(client, sid, "按当前条件做数据体检"))
    assert check[-1]["conversation"]["readiness"]["available_count"] == 10
    assert not any(call.url.path.endswith("/generate") for call in business.calls)
    business.readiness_state = "blocked"
    blocked = events(send(client, sid))
    assert any(row.get("code") == "data_not_ready" for row in blocked)
    assert not blocked[-1]["conversation"]["plans"]
    assert not any(call.url.path.endswith("/generate") for call in business.calls)


def test_clarification_retains_known_changes_and_short_reply_can_resume(context):
    client, business, _ = context
    sid = new_session(client)
    first = events(send(client, sid, "明天午餐1000人，预算少一点，安排菜单"))
    assert not any(row["type"] == "error" for row in first)
    conversation = first[-1]["conversation"]
    assert conversation["messages"][-1]["kind"] == "clarification"
    assert conversation["messages"][-1]["suggestions"]
    pending = conversation["pending_task"]
    assert pending["field"] == "budget_per_person"
    assert pending["parameters"]["diner_count"] == 1000
    assert not any(call.url.path.endswith("/generate") for call in business.calls)
    result = events(
        client.post(
            f"/agent-api/v1/sessions/{sid}/messages",
            json={
                "content": "7元",
                "parameters": pending["parameters"],
                "expected_revision": 0,
                "request_id": str(uuid4()),
            },
        )
    )[-1]["conversation"]
    assert result["pending_task"] is None
    assert result["plans"][0]["parameters"]["diner_count"] == 1000
    assert result["plans"][0]["parameters"]["budget_per_person"] == "7"


def test_ambiguous_meal_preserves_people_and_budget_without_computing(context):
    client, business, _ = context
    result = events(send(client, new_session(client), "明天午餐或晚餐1200人，每人9元安排菜单"))[-1][
        "conversation"
    ]
    assert result["pending_task"]["field"] == "meal_type"
    assert result["pending_task"]["parameters"]["diner_count"] == 1200
    assert result["pending_task"]["parameters"]["budget_per_person"] == "9"
    assert not any(call.url.path.endswith("/generate") for call in business.calls)


def test_clarification_can_be_cancelled_without_changing_old_plan(context):
    client, business, _ = context
    sid = new_session(client)
    events(send(client, sid))
    events(send(client, sid, "预算少一点", revision=1))
    count = len(business.calls)
    result = events(send(client, sid, "取消补充", revision=1))[-1]["conversation"]
    assert result["pending_task"] is None and len(result["plans"]) == 1
    assert all(call.url.path.endswith("auth/me") for call in business.calls[count:])


@pytest.mark.parametrize(
    "content",
    [
        "安排2026-02-30菜单",
        "明天午餐和晚餐安排菜单",
        "安排800至1000人菜单",
        "安排素食菜单",
        "每人预算-1元安排菜单",
        "安排明天午餐，每人预算8至10元",
        "安排明天午餐，每人预算8到10元",
        "安排明天午餐，每人预算8~10元",
        "安排明天午餐，每人预算8～10元",
        "安排菜单，每人预算8至10",
        "安排菜单，每人预算8到10",
        "安排菜单，每人预算8~10",
        "安排菜单，每人预算8～10",
    ],
)
def test_unsupported_or_conflicting_inputs_require_clarification(content):
    from zhiwei_agent.errors import TaskClarification

    with pytest.raises(TaskClarification):
        parameters_from_text(content, PlanParameters(on_date=TODAY), DISHES)


def test_relative_budget_changes_and_routing_are_explicit():
    from zhiwei_agent.rules import intent

    base = PlanParameters(on_date=TODAY, budget_per_person="8")
    assert parameters_from_text("每人预算减少1元", base, DISHES).budget_per_person == 7
    assert intent("按最近数据安排明天菜单") == "generate_menu_plan"
    assert intent("解释当前菜单") == "get_current_plan"
    assert intent("核查最近14天记录") == "review_operations"


def test_mixed_restore_and_exclude_apply_to_their_own_dishes():
    dishes = [{"id": "a", "name": "番茄炒蛋"}, {"id": "b", "name": "清炒青菜"}]
    # Use valid UUIDs, as the public parameter contract requires.
    dishes[0]["id"], dishes[1]["id"] = str(uuid4()), str(uuid4())
    base = PlanParameters(on_date=TODAY, excluded_dish_ids=[dishes[0]["id"]])
    result = parameters_from_text("不再排除番茄炒蛋但去掉清炒青菜，重新安排菜单", base, dishes)
    assert list(map(str, result.excluded_dish_ids)) == [dishes[1]["id"]]
    reset = parameters_from_text("清空排除但去掉清炒青菜，重新安排菜单", base, dishes)
    assert list(map(str, reset.excluded_dish_ids)) == [dishes[1]["id"]]


def test_partial_answer_keeps_other_questions_and_only_executes_when_all_resolved(context):
    client, business, _ = context
    sid = new_session(client)
    conversation = events(send(client, sid, "安排明天午餐或晚餐，1000人或1200人，每人8元"))[-1][
        "conversation"
    ]
    assert {row["field"] for row in conversation["pending_task"]["questions"]} == {
        "meal_type",
        "diner_count",
    }

    def reply(content):
        return events(
            client.post(
                f"/agent-api/v1/sessions/{sid}/messages",
                json={
                    "content": content,
                    "parameters": conversation["pending_task"]["parameters"],
                    "expected_revision": 0,
                    "request_id": str(uuid4()),
                },
            )
        )[-1]["conversation"]

    conversation = reply("1000人")
    assert not conversation["plans"]
    assert conversation["pending_task"]["field"] == "meal_type"
    assert conversation["pending_task"]["parameters"]["diner_count"] == 1000
    assert not any(call.url.path.endswith("/generate") for call in business.calls)
    # An unrelated explanation request must not erase the pending meal question.
    conversation = reply("解释当前方案")
    assert conversation["pending_task"]["field"] == "meal_type"
    conversation = reply("午餐")
    assert conversation["pending_task"] is None
    assert conversation["plans"][0]["parameters"]["diner_count"] == 1000
    assert conversation["plans"][0]["parameters"]["meal_type"] == "LUNCH"


def test_cancellation_never_calls_model_or_business_tools(tmp_path, monkeypatch):
    business = BusinessFake()
    cfg = Settings(
        data_path=tmp_path / "cancel.sqlite3",
        mode="model",
        model_base_url="https://model.invalid/v1",
        model_name="test",
        model_api_key="secret",
        _env_file=None,
    )

    async def forbidden(*args):
        raise AssertionError("cancel must bypass the model")

    monkeypatch.setattr("zhiwei_agent.model.complete", forbidden)
    with TestClient(create_app(cfg, httpx.MockTransport(business))) as client:
        client.cookies.set("canteen_token", "owner")
        result = events(send(client, new_session(client), "不要再生成菜单"))[-1]["conversation"]
        assert "已取消" in result["messages"][-1]["content"]
        assert not result["plans"]
        assert all(call.url.path.endswith("auth/me") for call in business.calls)


def test_model_can_ask_a_structured_question_without_generating(tmp_path, monkeypatch):
    business = BusinessFake()
    cfg = Settings(
        data_path=tmp_path / "question.sqlite3",
        mode="model",
        model_base_url="https://model.invalid/v1",
        model_name="test",
        model_api_key="secret",
        _env_file=None,
    )

    async def clarify(settings, messages):
        return {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "question",
                    "type": "function",
                    "function": {
                        "name": "clarify_task",
                        "arguments": json.dumps(
                            {
                                "question": "本次每人预算是多少？",
                                "field": "budget_per_person",
                                "known_parameters": {"diner_count": 1000},
                                "options": [
                                    {"label": "每人7元", "content": "预算每人7元，安排菜单"}
                                ],
                            }
                        ),
                    },
                }
            ],
        }

    monkeypatch.setattr("zhiwei_agent.model.complete", clarify)
    with TestClient(create_app(cfg, httpx.MockTransport(business))) as client:
        client.cookies.set("canteen_token", "owner")
        result = events(send(client, new_session(client), "改成1000人，预算少一点"))
        assert not any(row["type"] == "error" for row in result)
        conversation = result[-1]["conversation"]
        assert conversation["messages"][-1]["kind"] == "clarification"
        assert conversation["pending_task"]["field"] == "budget_per_person"
        assert conversation["pending_task"]["parameters"]["diner_count"] == 1000
        assert not any(call.url.path.endswith("/generate") for call in business.calls)


def test_model_cannot_generate_until_user_resolves_pending_budget(tmp_path, monkeypatch):
    business = BusinessFake()
    cfg = Settings(
        data_path=tmp_path / "pending-model.sqlite3",
        mode="model",
        model_base_url="https://model.invalid/v1",
        model_name="test",
        model_api_key="secret",
        _env_file=None,
    )
    calls = 0

    async def mistaken(settings, messages):
        nonlocal calls
        calls += 1
        if calls == 1:
            name, arguments = (
                "clarify_task",
                {
                    "question": "请指定每人预算",
                    "field": "budget_per_person",
                    "known_parameters": {"diner_count": 1000},
                },
            )
        elif calls in {2, 3}:
            name, arguments = "generate_menu_plan", {"diner_count": 1200, "budget_per_person": "9"}
        else:
            return {"role": "assistant", "content": "请核对已生成的方案。"}
        return {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": str(calls),
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(arguments)},
                }
            ],
        }

    monkeypatch.setattr("zhiwei_agent.model.complete", mistaken)
    with TestClient(create_app(cfg, httpx.MockTransport(business))) as client:
        client.cookies.set("canteen_token", "owner")
        sid = new_session(client)
        result = events(send(client, sid, "1000人，预算少一点安排菜单"))[-1]["conversation"]

        def reply(content):
            return events(
                client.post(
                    f"/agent-api/v1/sessions/{sid}/messages",
                    json={
                        "content": content,
                        "parameters": result["pending_task"]["parameters"],
                        "expected_revision": 0,
                        "request_id": str(uuid4()),
                    },
                )
            )[-1]["conversation"]

        result = reply("改成1200人")
        assert not result["plans"] and result["pending_task"]["field"] == "budget_per_person"
        assert result["pending_task"]["parameters"]["diner_count"] == 1200
        assert not any(call.url.path.endswith("/generate") for call in business.calls)
        result = reply("7元")
        assert result["pending_task"] is None
        assert result["plans"][0]["parameters"]["budget_per_person"] == "7"
        assert result["plans"][0]["parameters"]["diner_count"] == 1200


def test_report_is_owner_scoped_escaped_offline_and_uses_saved_snapshot(context):
    client, business, app = context
    sid = new_session(client)
    events(send(client, sid))
    saved = app.state.store.get(sid, "owner")
    version = saved.plans[0]
    version.result["dishes"][0]["dish_name"] = '<script>alert("unsafe")</script>'
    version.result["missing_price_warning"] = "未录单价"
    version.data_notice = "生成时的合成数据说明"
    app.state.store.save(saved, "owner")
    before = len(business.calls)
    report = client.get(f"/agent-api/v1/sessions/{sid}/report.html?revision=1")
    assert report.status_code == 200
    assert 'attachment; filename="zhiwei-plan-v1.html"' == report.headers["content-disposition"]
    assert "default-src 'none'" in report.headers["content-security-policy"]
    assert "<script>" not in report.text and "&lt;script&gt;" in report.text
    assert "生成时的合成数据说明" in report.text and "已知价格部分合计" in report.text
    assert PLAN["total_cost"] in report.text and "待人工确认的草案" in report.text
    assert all(call.url.path.endswith("auth/me") for call in business.calls[before:])
    assert client.get(f"/agent-api/v1/sessions/{sid}/report.html?revision=2").status_code == 404
    client.cookies.set("canteen_token", "other")
    assert client.get(f"/agent-api/v1/sessions/{sid}/report.html").status_code == 404


def test_model_base_url_cannot_hide_an_external_http_host_in_userinfo(tmp_path):
    for address in (
        "http://localhost:80@attacker.invalid/v1",
        "http://attacker.invalid/v1",
        "https:///v1",
    ):
        with pytest.raises(ValueError):
            Settings(data_path=tmp_path / "url.sqlite3", model_base_url=address, _env_file=None)


def test_model_calls_are_whitelisted_and_persisted(tmp_path, monkeypatch):
    business = BusinessFake()
    cfg = Settings(
        data_path=tmp_path / "model.sqlite3",
        mode="model",
        model_base_url="https://model.invalid/v1",
        model_name="test-model",
        model_api_key="never-return-this",
        _env_file=None,
    )
    responses = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "tool-1",
                    "type": "function",
                    "function": {
                        "name": "generate_menu_plan",
                        "arguments": json.dumps(
                            {
                                "on_date": str(TODAY + timedelta(days=1)),
                                "diner_count": 1000,
                            }
                        ),
                    },
                }
            ],
        },
        {"role": "assistant", "content": "工具计算已完成，请人工核对。"},
    ]

    async def fake_complete(settings, messages):
        assert "never-return-this" not in json.dumps(messages, ensure_ascii=False)
        if len(responses) == 1:
            assert messages[-1]["role"] == "tool"
        return responses.pop(0)

    monkeypatch.setattr("zhiwei_agent.model.complete", fake_complete)
    with TestClient(create_app(cfg, httpx.MockTransport(business))) as client:
        client.cookies.set("canteen_token", "owner")
        sid = new_session(client)
        result = events(
            client.post(
                f"/agent-api/v1/sessions/{sid}/messages",
                json={
                    "content": "改成1000人，其余不变",
                    "parameters": {
                        "on_date": str(TODAY + timedelta(days=1)),
                        "meal_type": "DINNER",
                        "diner_count": 800,
                        "budget_per_person": "12",
                        "excluded_dish_ids": [DISHES[0]["id"]],
                    },
                    "expected_revision": 0,
                    "request_id": str(uuid4()),
                },
            )
        )[-1]["conversation"]
        assert result["plans"] and "整餐人均营养供给" in result["messages"][-1]["content"]
        assert result["plans"][0]["result"]["total_cost"] in result["messages"][-1]["content"]
        assert "never-return-this" not in client.get("/agent-api/v1/status").text
        assert not any(call.url.path.endswith("/publish") for call in business.calls)
        generated = next(call for call in business.calls if call.url.path.endswith("/generate"))
        assert generated.url.params["meal_type"] == "DINNER"
        assert generated.url.params["diner_count"] == "1000"
        assert json.loads(generated.content) == {
            "budget_per_person": "12",
            "excluded_dish_ids": [DISHES[0]["id"]],
        }
        assert result["plans"][0]["parameters"]["meal_type"] == "DINNER"


def test_model_failure_preserves_completed_plan(tmp_path, monkeypatch):
    from zhiwei_agent.errors import AgentError

    business = BusinessFake()
    cfg = Settings(
        data_path=tmp_path / "failed-model.sqlite3",
        mode="model",
        model_base_url="https://model.invalid/v1",
        model_name="test-model",
        model_api_key="secret",
        _env_file=None,
    )
    count = 0

    async def flaky(settings, messages):
        nonlocal count
        count += 1
        if count == 1:
            return {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "tool-1",
                        "type": "function",
                        "function": {
                            "name": "generate_menu_plan",
                            "arguments": json.dumps(
                                {"on_date": str(TODAY + timedelta(days=1)), "diner_count": 800}
                            ),
                        },
                    }
                ],
            }
        raise AgentError("模型暂时不可用", 503, "model_unavailable")

    monkeypatch.setattr("zhiwei_agent.model.complete", flaky)
    with TestClient(create_app(cfg, httpx.MockTransport(business))) as client:
        client.cookies.set("canteen_token", "owner")
        sid = new_session(client)
        result = events(send(client, sid))
        assert any(row.get("code") == "model_unavailable" for row in result)
        assert result[-1]["conversation"]["plans"][0]["revision"] == 1
        assert client.get(f"/agent-api/v1/sessions/{sid}/purchase.csv").status_code == 200


def test_model_cannot_invoke_publish_or_arbitrary_network(tmp_path, monkeypatch):
    business = BusinessFake()
    cfg = Settings(
        data_path=tmp_path / "untrusted-model.sqlite3",
        mode="model",
        model_base_url="https://model.invalid/v1",
        model_name="test-model",
        model_api_key="secret",
        _env_file=None,
    )
    replies = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "bad",
                    "type": "function",
                    "function": {
                        "name": "publish",
                        "arguments": '{"url":"https://attacker.invalid"}',
                    },
                }
            ],
        },
        {"role": "assistant", "content": "该操作没有开放。"},
    ]

    async def untrusted(settings, messages):
        return replies.pop(0)

    monkeypatch.setattr("zhiwei_agent.model.complete", untrusted)
    with TestClient(create_app(cfg, httpx.MockTransport(business))) as client:
        client.cookies.set("canteen_token", "owner")
        result = events(send(client, new_session(client)))
        assert result[-1]["conversation"]["messages"][-1]["trace"][0]["status"] == "error"
        assert not result[-1]["conversation"]["plans"]
        assert all(call.url.path.endswith("auth/me") for call in business.calls)


def test_cookie_is_never_saved_and_only_business_token_forwarded(context):
    client, business, app = context
    client.cookies.set("canteen_token", "sensitive-cookie-value")
    client.cookies.set("unrelated", "must-not-be-forwarded")
    sid = new_session(client)
    events(send(client, sid))
    assert all(
        "must-not-be-forwarded" not in request.headers.get("cookie", "")
        for request in business.calls
    )
    assert b"sensitive-cookie-value" not in app.state.store.path.read_bytes()


def test_csv_prevents_spreadsheet_formula_execution(context):
    import csv
    import io

    client, _, app = context
    sid = new_session(client)
    events(send(client, sid))
    session = app.state.store.get(sid, "owner")
    session.plans[0].result["requirements"][0]["name"] = '=HYPERLINK("https://attacker.invalid")'
    app.state.store.save(session, "owner")
    response = client.get(f"/agent-api/v1/sessions/{sid}/purchase.csv")
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert any(row and row[0].startswith("'=HYPERLINK") for row in rows)

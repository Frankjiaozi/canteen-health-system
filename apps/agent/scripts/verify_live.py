"""人工执行的独立开发联调；真实模型可能计费，禁止指向正式业务环境。"""

import argparse
import asyncio
import csv
import io
import json
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps/agent"))
API = "http://127.0.0.1:8002/api/v1"
AGENT = "http://127.0.0.1:8001/agent-api/v1"


class LiveCheck:
    def __init__(self, output: Path, resume: bool):
        self.output = output
        output.mkdir(parents=True, exist_ok=True)
        self.state_path = output / "live-state.json"
        if self.state_path.exists() and not resume:
            raise SystemExit(
                "已有联调记录，请使用 --resume 或指定新的 --output 目录；不会覆盖已有成果"
            )
        self.state = (
            json.loads(self.state_path.read_text(encoding="utf-8"))
            if resume
            else {
                "checks": [],
                "conversation": None,
                "model_calls": "real",
                "data": "synthetic_demo",
            }
        )
        self.client = httpx.Client(timeout=200, trust_env=False)
        self.login(self.client, "recorder")
        status = self.get(AGENT + "/status")
        assert status["mode"] == "model", "本轮要求真实模型模式"
        assert "独立开发" in status["data_notice"], "Agent 未指向明确标记的隔离开发环境"
        self.state["model_name"] = status["model_name"]

    @staticmethod
    def login(client, username):
        response = client.post(
            API + "/auth/login", json={"username": username, "password": "canteen@2026"}
        )
        assert response.status_code == 200, "独立开发账号登录失败；不会重置账号"
        return response.json()

    def get(self, url, **kwargs):
        response = self.client.get(url, **kwargs)
        response.raise_for_status()
        return response.json()

    def save(self):
        self.state_path.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def record(self, name, **details):
        self.state["checks"].append({"name": name, "passed": True, **details})
        self.save()
        print(
            json.dumps({"check": name, "passed": True, **details}, ensure_ascii=False), flush=True
        )

    def new(self):
        response = self.client.post(AGENT + "/sessions")
        response.raise_for_status()
        return response.json()

    def send(self, conversation, content, parameters):
        payload = {
            "content": content,
            "parameters": parameters,
            "expected_revision": len(conversation["plans"]),
            "request_id": str(uuid4()),
        }
        events = []
        with self.client.stream(
            "POST", AGENT + f"/sessions/{conversation['id']}/messages", json=payload
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    events.append(json.loads(line))
        assert events and events[-1]["type"] == "done", "任务未收到 done，不能宣称成功"
        result = events[-1]["conversation"]
        self.state["last_events"] = events
        self.state["last_request"] = payload
        self.state["last_session_id"] = result["id"]
        self.save()
        print(
            json.dumps(
                {
                    "session": result["id"],
                    "revision": len(result["plans"]),
                    "kind": result["messages"][-1]["kind"],
                    "answer": result["messages"][-1]["content"][:1500],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return result

    def validate_plan(self, conversation, count, budget):
        version = conversation["plans"][-1]
        plan = version["result"]
        assert conversation["messages"][-1]["kind"] == "message", "本轮没有正常完成，请查看记录"
        assert version["parameters"]["diner_count"] == count
        assert Decimal(version["parameters"]["budget_per_person"]) == Decimal(budget)
        assert plan["diner_count"] == count
        assert Decimal(plan["budget"]) == Decimal(count) * Decimal(budget)
        known = sum(
            (
                Decimal(row["estimated_cost"])
                for row in plan["requirements"]
                if row["estimated_cost"] is not None
            ),
            Decimal(0),
        )
        if plan["total_cost"] is not None:
            assert known == Decimal(plan["total_cost"]), "采购行金额和快照合计不一致"
        assert version["publication"] is None, "生成不得自动发布"

    def dialogue(self):
        conversation = self.state.get("conversation") or self.new()
        if not self.state.get("on_date"):
            today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
            for offset in range(1, 15):
                candidate = str(today + timedelta(days=offset))
                sheet = self.get(
                    API + f"/collection/logs/{candidate}", params={"meal_type": "LUNCH"}
                )
                if not sheet["saved"] and not sheet["menu_confirmed"]:
                    self.state["on_date"] = candidate
                    break
            assert self.state.get("on_date"), "没有空闲功能验证餐次，拒绝覆盖已有菜单"
        on_date = self.state["on_date"]
        if not conversation["plans"]:
            forecast = self.get(
                AGENT + "/diner-forecast", params={"on_date": on_date, "meal_type": "LUNCH"}
            )
            self.record(
                "forecast",
                predicted=forecast["predicted_diner_count"],
                lower=forecast["lower"],
                upper=forecast["upper"],
            )
            parameters = {
                "on_date": on_date,
                "meal_type": "LUNCH",
                "diner_count": 800,
                "budget_per_person": "8.00",
                "excluded_dish_ids": [],
            }
            conversation = self.send(
                conversation, f"安排{on_date}午餐800人，每人预算8元", parameters
            )
            self.state["conversation"] = conversation
            self.save()
            assert len(conversation["plans"]) == 1, "首次生成没有得到方案"
            self.validate_plan(conversation, 800, "8")
            self.record(
                "generate",
                revision=1,
                dish_count=len(conversation["plans"][-1]["result"]["dishes"]),
            )
        if len(conversation["plans"]) == 1:
            conversation = self.send(
                conversation,
                "人数改为1000人，每人预算改为9元，其余条件不变",
                conversation["plans"][-1]["parameters"],
            )
            self.state["conversation"] = conversation
            self.save()
            assert len(conversation["plans"]) == 2, "修改条件没有生成第二版"
            self.validate_plan(conversation, 1000, "9")
            self.record("modify_conditions", revision=2)
        if len(conversation["plans"]) == 2:
            target = next(
                row
                for row in conversation["plans"][-1]["result"]["dishes"]
                if row["category_label"] != "主食"
            )
            self.state["excluded_dish"] = target
            conversation = self.send(
                conversation,
                f"不要{target['dish_name']}，其余条件不变，请重新安排",
                conversation["plans"][-1]["parameters"],
            )
            self.state["conversation"] = conversation
            self.save()
            assert len(conversation["plans"]) == 3, "排除菜品没有生成第三版"
            self.validate_plan(conversation, 1000, "9")
            assert target["dish_id"] not in {
                row["dish_id"] for row in conversation["plans"][-1]["result"]["dishes"]
            }
            self.record("exclude_dish", revision=3, excluded_name=target["dish_name"])
        sid = conversation["id"]
        csv_response = self.client.get(AGENT + f"/sessions/{sid}/purchase.csv?revision=1")
        html_response = self.client.get(AGENT + f"/sessions/{sid}/report.html?revision=1")
        assert csv_response.status_code == html_response.status_code == 200
        rows = list(csv.reader(io.StringIO(csv_response.text.lstrip("\ufeff"))))
        total_row = next(row for row in rows if row and row[0] in {"合计", "已知价格部分合计"})
        assert Decimal(total_row[-1]) == Decimal(conversation["plans"][0]["result"]["total_cost"])
        (self.output / "plan-v1.csv").write_bytes(csv_response.content)
        (self.output / "plan-v1.html").write_text(html_response.text, encoding="utf-8")
        user_messages = [row for row in conversation["messages"] if row["role"] == "user"]
        replay_payload = {
            "content": user_messages[2]["content"],
            "parameters": conversation["plans"][1]["parameters"],
            "expected_revision": 2,
            "request_id": user_messages[2]["id"],
        }
        replay = self.client.post(AGENT + f"/sessions/{sid}/messages", json=replay_payload)
        replay_events = [json.loads(line) for line in replay.text.splitlines() if line]
        assert (
            replay.status_code == 200
            and len(replay_events) == 1
            and replay_events[0]["type"] == "done"
        )
        assert len(replay_events[0]["conversation"]["plans"]) == 3
        self.record("historical_exports_and_request_replay", revision=1)

    def safety(self):
        conversation = self.state["conversation"]
        sid = conversation["id"]
        with httpx.Client(timeout=20, trust_env=False) as other:
            self.login(other, "canteen")
            for suffix in ("", "/purchase.csv", "/report.html"):
                assert other.get(AGENT + f"/sessions/{sid}{suffix}").status_code == 404
        with httpx.Client(timeout=20, trust_env=False) as school:
            self.login(school, "school")
            assert school.get(AGENT + "/status").json()["can_plan"] is False
            assert (
                school.post(AGENT + f"/sessions/{sid}/publish", json={"revision": 3}).status_code
                == 403
            )
            assert (
                school.post(AGENT + f"/sessions/{sid}/undo", json={"revision": 3}).status_code
                == 403
            )
        self.record("account_isolation_and_readonly_role")

    def extended(self):
        """复用原三版证据，再验证重启恢复、自动预测、多轮澄清及缺数据。"""
        completed = {row["name"] for row in self.state["checks"] if row["passed"]}
        conversation = self.get(AGENT + f"/sessions/{self.state['conversation']['id']}")
        assert len(conversation["plans"]) == 3 and conversation["plans"][-1]["undone"]
        if "restart_recovery_and_grounded_explanation" not in completed:
            explained = self.send(
                conversation, "解释当前方案的计算依据", conversation["plans"][-1]["parameters"]
            )
            answer = explained["messages"][-1]["content"]
            assert "整餐人均营养供给" in answer and "已撤回" in answer
            assert "单份口径" not in answer and "预算占用率" not in answer
            self.state["conversation"] = explained
            self.record("restart_recovery_and_grounded_explanation")
        on_date = self.state["on_date"]
        parameters = {
            "on_date": on_date,
            "meal_type": "LUNCH",
            "diner_count": None,
            "budget_per_person": "8.00",
            "excluded_dish_ids": [],
        }
        if "automatic_diner_forecast" not in completed:
            prediction = self.get(
                AGENT + "/diner-forecast", params={"on_date": on_date, "meal_type": "LUNCH"}
            )
            predicted = self.send(
                self.new(), f"安排{on_date}午餐，人数使用系统预测，每人预算8元", parameters
            )
            assert len(predicted["plans"]) == 1
            self.validate_plan(predicted, prediction["predicted_diner_count"], "8")
            assert "整餐人均营养供给" in predicted["messages"][-1]["content"]
            self.record("automatic_diner_forecast", predicted=prediction["predicted_diner_count"])
        if "clarification_and_short_answer_resume" not in completed:
            pending = self.send(self.new(), f"安排{on_date}午餐1000人，预算少一点", parameters)
            assert not pending["plans"] and pending["pending_task"]["field"] == "budget_per_person"
            assert pending["pending_task"]["parameters"]["diner_count"] == 1000
            answered = self.send(pending, "9元", pending["pending_task"]["parameters"])
            assert len(answered["plans"]) == 1 and answered["pending_task"] is None
            self.validate_plan(answered, 1000, "9")
            self.record("clarification_and_short_answer_resume")
        breakfast_parameters = {**parameters, "meal_type": "BREAKFAST"}
        report = self.get(
            API + "/menu-plan/readiness", params={"on_date": on_date, "meal_type": "BREAKFAST"}
        )
        if report["state"] == "blocked":
            checked = self.send(
                self.new(),
                f"请检查{on_date}早餐的数据准备情况，列出缺项，不要生成菜单",
                breakfast_parameters,
            )
            assert not checked["plans"]
            assert checked["readiness"] and checked["readiness"]["state"] == "blocked"
            self.record(
                "blocked_data_explained_without_generation", issue_count=report["issue_count"]
            )
        else:
            self.record("breakfast_readiness_available", state=report["state"])

    def read_tools(self):
        """真实业务 HTTP 工具验收，不调用模型、不接触业务数据库。"""
        from zhiwei_agent.business import BusinessClient
        from zhiwei_agent.config import Settings
        from zhiwei_agent.schemas import Conversation, PlanParameters
        from zhiwei_agent.tools import Tools

        cookie_name = Settings().cookie_name
        token = self.client.cookies.get(cookie_name)
        logs = self.get(API + "/collection/logs", params={"page_size": 100})["items"]
        latest = max(logs, key=lambda row: row["date"])
        current = self.state["conversation"]
        dish_name = current["plans"][-1]["result"]["dishes"][0]["dish_name"]

        async def execute():
            business = BusinessClient(API, cookie_name, token)
            tools = Tools(
                business,
                Conversation.model_validate(current),
                "RECORDER",
                PlanParameters.model_validate(current["plans"][-1]["parameters"]),
            )
            results = {}
            try:
                for name, args in [
                    ("get_dashboard", {"days": 14}),
                    ("get_menu_day", {"on_date": latest["date"], "meal_type": latest["meal_type"]}),
                    ("get_dish_recipe", {"keyword": dish_name}),
                    ("list_ingredients", {"keyword": "大白菜"}),
                    ("list_holidays", {"year": 2026, "month": 10}),
                    ("review_operations", {"days": 7}),
                ]:
                    result = await tools.execute(name, args)
                    assert isinstance(result, dict)
                    results[name] = result
            finally:
                await business.close()
            return results

        results = asyncio.run(execute())
        (self.output / "read-tools.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        for tool_name in results:
            self.record("business_http_" + tool_name)

    def publication(self):
        conversation = self.state["conversation"]
        sid = conversation["id"]
        version = conversation["plans"][-1]
        on_date = version["parameters"]["on_date"]
        sheet_url = API + f"/collection/logs/{on_date}"
        before = self.get(sheet_url, params={"meal_type": "LUNCH"})
        assert not before["saved"] and not before["menu_confirmed"], (
            "发布验收仅允许原本没有菜单的功能验证餐次"
        )
        competitor_id = None
        agent_published = False
        try:
            competitor = self.client.post(
                API + "/menu-plan/generate",
                params={"on_date": on_date, "meal_type": "LUNCH", "diner_count": 1000},
                json={
                    "budget_per_person": "9",
                    "excluded_dish_ids": version["parameters"]["excluded_dish_ids"],
                },
            )
            competitor.raise_for_status()
            plan = competitor.json()
            published = self.client.post(
                API + f"/menu-plan/{plan['suggestion_id']}/publish",
                json={
                    "snapshot_token": plan["snapshot_token"],
                    "expected_menu_token": plan["expected_menu_token"],
                },
            )
            published.raise_for_status()
            competitor_id = plan["suggestion_id"]
            conflict = self.client.post(AGENT + f"/sessions/{sid}/publish", json={"revision": 3})
            assert conflict.status_code == 409, "过期正式菜单版本必须拒绝发布"
            saved = self.get(AGENT + f"/sessions/{sid}")
            assert saved["plans"][-1]["publication"] is None
            restored = self.client.post(API + f"/menu-plan/{competitor_id}/undo")
            restored.raise_for_status()
            competitor_id = None
            self.record("publication_conflict", status=409)
            confirmed = self.client.post(AGENT + f"/sessions/{sid}/publish", json={"revision": 3})
            confirmed.raise_for_status()
            agent_published = True
            receipt = confirmed.json()["plans"][-1]["publication"]
            again = self.client.post(AGENT + f"/sessions/{sid}/publish", json={"revision": 3})
            again.raise_for_status()
            assert again.json()["plans"][-1]["publication"]["already_published"] is True
            sheet = self.get(sheet_url, params={"meal_type": "LUNCH"})
            expected = {row["dish_id"] for row in version["result"]["dishes"]}
            assert {row["dish_id"] for row in sheet["dishes"] if row["selected"]} == expected
            wrong = self.client.post(AGENT + f"/sessions/{sid}/undo", json={"revision": 2})
            assert wrong.status_code == 409
            undone = self.client.post(AGENT + f"/sessions/{sid}/undo", json={"revision": 3})
            undone.raise_for_status()
            agent_published = False
            after = self.get(sheet_url, params={"meal_type": "LUNCH"})
            assert not after["saved"] and not after["menu_confirmed"]
            csv_text = self.client.get(AGENT + f"/sessions/{sid}/purchase.csv?revision=3").text
            html_text = self.client.get(AGENT + f"/sessions/{sid}/report.html?revision=3").text
            assert "已撤回" in csv_text and "已撤回" in html_text
            assert (
                self.client.post(
                    AGENT + f"/sessions/{sid}/publish", json={"revision": 3}
                ).status_code
                == 409
            )
            self.state["conversation"] = undone.json()
            self.record("publish_idempotency_undo_and_restore", dish_count=receipt["dish_count"])
        finally:
            if competitor_id:
                cleanup = self.client.post(API + f"/menu-plan/{competitor_id}/undo")
                cleanup.raise_for_status()
            if agent_published:
                cleanup = self.client.post(AGENT + f"/sessions/{sid}/undo", json={"revision": 3})
                cleanup.raise_for_status()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument(
        "--publish-demo", action="store_true", help="在隔离开发库执行发布冲突、发布及撤回验收"
    )
    parser.add_argument(
        "--resume", action="store_true", help="沿用本次验收保存的方案，避免重复模型调用"
    )
    parser.add_argument(
        "--stage",
        choices=["dialogue", "safety", "publication", "extended", "read-tools", "all"],
        default="all",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "output/agent-live-check-20261019")
    args = parser.parse_args()
    if not args.run:
        parser.error("需显式传入 --run；真实模型可能计费")
    if args.stage == "publication" and not args.publish_demo:
        parser.error("发布验收还需要 --publish-demo，且只允许已确认的隔离开发环境")
    run = LiveCheck(args.output, args.resume)
    try:
        if args.stage in {"dialogue", "all"}:
            run.dialogue()
        if args.stage in {"safety", "all"}:
            run.safety()
        if args.publish_demo and args.stage in {"publication", "all"}:
            run.publication()
        if args.stage == "extended":
            run.extended()
        if args.stage == "read-tools":
            run.read_tools()
    finally:
        run.save()
        run.client.close()


if __name__ == "__main__":
    main()

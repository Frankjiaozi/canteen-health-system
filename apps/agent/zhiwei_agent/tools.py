"""可审计的工具白名单。模型没有发布、SQL、文件或任意 URL 工具。"""

from datetime import datetime, timedelta
from decimal import Decimal
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo

from . import rules
from .business import BusinessClient
from .errors import AgentError, TaskClarification
from .schemas import (
    ClarificationArguments,
    Conversation,
    DishArguments,
    EmptyArguments,
    PlanParameters,
    PlanVersion,
    ReviewArguments,
    ReviewReport,
)
from .store import now

TOOL_LABELS = {
    "generate_menu_plan": "计算菜单、份数与采购",
    "review_operations": "核查近期供应记录",
    "list_dishes": "查询菜品库",
    "get_current_plan": "读取当前方案依据",
    "check_data_readiness": "检查菜库与历史数据",
    "clarify_task": "确认需要补充的条件",
}
ARGUMENTS = {
    "generate_menu_plan": PlanParameters,
    "review_operations": ReviewArguments,
    "list_dishes": DishArguments,
    "get_current_plan": EmptyArguments,
    "check_data_readiness": PlanParameters,
    "clarify_task": ClarificationArguments,
}
DESCRIPTIONS = {
    "generate_menu_plan": "安排菜单或根据新人数、预算、排除菜品重算。全部参数必须来自用户与当前任务条件。只创建待确认方案，不发布。排除菜品必须先查询真实ID。",
    "review_operations": "查询最近若干天采集记录，按系统异常标记、同餐次盐量偏离、剩餐比例和数据覆盖情况生成可核查事实。",
    "list_dishes": "查询在用菜品真实ID、名称、类别与配方版本。换菜前用于解析名称，最多返回100道。",
    "get_current_plan": "读取最近一次方案、约束、营养差距和采购金额，用于解释、对比或继续调整。",
    "check_data_readiness": "只读检查指定日期/餐次/排除条件的配方、单价、营养缺项、类别和历史准备情况。生成前先检查，指出来源与下一步；不能把检查通过当作真实性认证。",
    "clarify_task": "用户要求缺失、含糊、互相矛盾或不支持时，停止计算并问一个明确问题，可提供最多4个候选回复。候选不能被当作用户已同意；禁止用此工具伪装发布/付款/管理员授权。",
}


def definitions() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": DESCRIPTIONS[name],
                "parameters": model.model_json_schema(),
            },
        }
        for name, model in ARGUMENTS.items()
    ]


class Tools:
    def __init__(
        self,
        business: BusinessClient,
        conversation: Conversation,
        role: str,
        parameters: PlanParameters,
        data_notice: str = "",
        user_content: str = "",
    ):
        self.business, self.conversation, self.role = business, conversation, role
        self.parameters = parameters
        self.data_notice = data_notice
        self.user_content = user_content
        self.known_dishes: list[dict] = []
        self.generated = False
        self.readiness_parameters: dict | None = None

    async def execute(self, name: str, arguments: dict) -> Any:
        if name not in ARGUMENTS:
            raise AgentError("助手请求了未开放的工具", code="unknown_tool")
        # 模型可能只传改变的字段；省略不等于恢复午餐/默认预算/空排除。
        if name in {"generate_menu_plan", "check_data_readiness"}:
            arguments = {**self.parameters.model_dump(mode="json"), **arguments}
        if name == "generate_menu_plan" and self.conversation.pending_task:
            pending = self.conversation.pending_task
            questions = rules.remaining_questions(pending, self.parameters)
            # 模型传来的参数不是用户回答。只接受当前消息或面板中的明确补充。
            resolved = rules.parameters_from_text(
                rules.followup(self.user_content, pending.field),
                self.parameters,
                self.known_dishes,
                questions,
            )
            for field in {pending.field, *(row.field for row in pending.questions)}:
                if field in PlanParameters.model_fields:
                    arguments[field] = resolved.model_dump(mode="json")[field]
            self.conversation.pending_task = None
        parsed = ARGUMENTS[name].model_validate(arguments)
        if name == "clarify_task":
            if self.generated:
                raise AgentError(
                    "本轮已经生成方案，请先呈现该结果；下一轮再补充新的条件",
                    code="invalid_tool_sequence",
                )
            question = TaskClarification(
                parsed.question, parsed.field, [row.model_dump() for row in parsed.options]
            )
            question.parameters = PlanParameters.model_validate(
                {
                    **self.parameters.model_dump(mode="json"),
                    **parsed.known_parameters.model_dump(mode="json", exclude_unset=True),
                }
            ).model_dump(mode="json")
            raise question
        if name == "check_data_readiness":
            return await self.readiness(PlanParameters.model_validate(parsed.model_dump()))
        if name == "generate_menu_plan":
            if self.role not in {"RECORDER", "CANTEEN_ADMIN"}:
                raise AgentError("当前账号只能查看和分析，不能生成或发布菜单", 403, "forbidden")
            if self.generated:
                raise AgentError("一次请求最多生成一个方案，请先核对这版结果")
            parameters = PlanParameters.model_validate(parsed.model_dump())
            today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
            if parameters.on_date < today:
                raise AgentError("请安排今天或之后的菜单；历史日期可使用记录核查")
            if self.readiness_parameters != parameters.model_dump(mode="json"):
                await self.readiness(parameters)
            report = self.conversation.readiness
            if report and report["state"] == "blocked":
                raise AgentError(
                    "数据与条件暂不支持安排这一餐，请先查看数据体检中的阻塞项",
                    422,
                    "data_not_ready",
                    details={
                        "conflicts": [
                            row["title"]
                            for row in report["issues"]
                            if row["severity"] == "blocking"
                        ]
                    },
                )
            result = await self.business.request(
                "POST",
                "menu-plan/generate",
                params={
                    "on_date": str(parameters.on_date),
                    "meal_type": parameters.meal_type,
                    **({"diner_count": parameters.diner_count} if parameters.diner_count else {}),
                },
                json={
                    "budget_per_person": str(parameters.budget_per_person),
                    "excluded_dish_ids": [str(item) for item in parameters.excluded_dish_ids],
                },
            )
            if not isinstance(result.get("dishes"), list) or not result.get("snapshot_token"):
                raise AgentError(
                    "业务后端缺少完整方案快照，请更新业务后端后重试", 502, "contract_mismatch"
                )
            if parameters.diner_count is None:
                parameters.diner_count = result["diner_count"]
            self.conversation.plans.append(
                PlanVersion(
                    revision=self.conversation.revision + 1,
                    created_at=now(),
                    parameters=parameters,
                    result=result,
                    readiness=report,
                    data_notice=self.data_notice,
                )
            )
            self.generated = True
            return result
        if name == "get_current_plan":
            if not self.conversation.plans:
                return {"message": "当前尚未生成方案"}
            return self.conversation.plans[-1].model_dump(mode="json")
        if name == "list_dishes":
            result = await self.business.request(
                "GET", "dishes", params={"keyword": parsed.keyword, "page_size": 100}
            )
            self.known_dishes = result["items"]
            return {
                "items": [
                    {
                        key: item.get(key)
                        for key in (
                            "id",
                            "name",
                            "category_label",
                            "cooking_method_label",
                            "recipe_version",
                        )
                    }
                    for item in result["items"]
                ],
                "total": result["total"],
                "truncated": result["total"] > 100,
            }
        return await self.review(parsed.days)

    async def readiness(self, parameters: PlanParameters) -> dict:
        try:
            report = await self.business.request(
                "GET",
                "menu-plan/readiness",
                params=[
                    ("on_date", str(parameters.on_date)),
                    ("meal_type", parameters.meal_type),
                    *[("excluded_dish_ids", str(item)) for item in parameters.excluded_dish_ids],
                ],
            )
        except AgentError as exc:
            if exc.status == 404:
                raise AgentError(
                    "业务服务缺少数据体检接口，请更新业务后端后重试", 502, "contract_mismatch"
                ) from exc
            raise
        if report.get("state") not in {"blocked", "attention", "ready"}:
            raise AgentError("业务服务缺少数据体检接口，请更新后重试", 502, "contract_mismatch")
        self.conversation.readiness = report
        self.readiness_parameters = parameters.model_dump(mode="json")
        return report

    async def review(self, days: int) -> dict:
        end = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        start = end - timedelta(days=days - 1)
        result = await self.business.request(
            "GET",
            "collection/logs",
            params={"start": str(start), "end": str(end), "page_size": 100},
        )
        rows = result["items"]
        # 分页取完再统计，不把第一页误当成全部。
        for page in range(2, min(5, (result["total"] + 99) // 100) + 1):
            extra = await self.business.request(
                "GET",
                "collection/logs",
                params={"start": str(start), "end": str(end), "page_size": 100, "page": page},
            )
            rows.extend(extra["items"])
        issues, meal_salt = [], {}
        for row in rows:
            if row["diner_count"] > 0:
                meal_salt.setdefault(row["meal_type"], []).append(
                    Decimal(row["salt_total_g"]) / row["diner_count"]
                )
        for row in rows:
            link = f"/admin/collection?date={row['date']}&meal={row['meal_type']}"
            base = {
                "date": row["date"],
                "meal_type": row["meal_type"],
                "meal_label": row["meal_type_label"],
                "source": "每日采集",
                "link": link,
            }
            if row.get("anomaly_flags"):
                issues.append(
                    {
                        **base,
                        "kind": "flag",
                        "title": "记录包含异常标记",
                        "detail": "、".join(flag["label"] for flag in row["anomaly_flags"]),
                        "suggestion": "核对标记的具体背景；标记本身不能证明存在配方或营养问题。",
                    }
                )
            if row.get("waste_ratio") is not None and Decimal(row["waste_ratio"]) >= Decimal(
                "0.15"
            ):
                issues.append(
                    {
                        **base,
                        "kind": "waste",
                        "title": "剩餐比例需要核对",
                        "detail": f"记录值 {Decimal(row['waste_ratio']) * 100:.1f}% ≥ 15%（演示核查阈值）",
                        "suggestion": "核对出餐份数和剩餐称重，再查看是否存在临时停供等背景。",
                    }
                )
            values = meal_salt.get(row["meal_type"], [])
            if row["diner_count"] > 0 and len(values) >= 3:
                amount = Decimal(row["salt_total_g"]) / row["diner_count"]
                baseline = median(values)
                if baseline > 0 and amount > baseline * Decimal("1.5"):
                    issues.append(
                        {
                            **base,
                            "kind": "salt",
                            "title": "盐量偏离同餐次历史",
                            "detail": f"本餐 {amount:.2f} g/人次，同餐次中位数 {baseline:.2f} g/人次，超过 1.5 倍（演示核查阈值）",
                            "suggestion": "先核对盐总量和就餐人次；此项不能直接判断健康风险或认定厨师多放盐。",
                        }
                    )
            if row["diner_count"] == 0:
                issues.append(
                    {
                        **base,
                        "kind": "missing",
                        "title": "就餐人次为零",
                        "detail": "无法计算每人次用量",
                        "suggestion": "核对是否停餐或漏录，保留实际背景。",
                    }
                )
        present = {row["date"] for row in rows}
        review = {
            "start": str(start),
            "end": str(end),
            "days": days,
            "record_count": len(rows),
            "days_with_records": len(present),
            "missing_dates": [
                str(start + timedelta(days=index))
                for index in range(days)
                if str(start + timedelta(days=index)) not in present
            ],
            "issues": issues,
            "rows": rows,
            "truncated": len(rows) < result["total"],
            "note": "仅列出需要人工核查的记录，不认定原因。无记录日期可能未营业；15% 与 1.5 倍为演示核查阈值，不是医学或行业合规标准。",
        }
        self.conversation.review = ReviewReport.model_validate(review)
        return review

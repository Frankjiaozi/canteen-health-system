"""可审计的工具白名单。模型没有发布、SQL、文件或任意 URL 工具。"""

import asyncio
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
    DashboardArguments,
    DishArguments,
    DishRecipeArguments,
    EmptyArguments,
    HolidayArguments,
    IngredientArguments,
    MenuDayArguments,
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
    "get_dashboard": "查看看板指标",
    "get_menu_day": "查看当日供应与营养",
    "get_dish_recipe": "查看菜品配方",
    "list_ingredients": "查询食材营养",
    "list_holidays": "核对节假日与调休",
    "get_current_plan": "读取当前方案依据",
    "check_data_readiness": "检查菜库与历史数据",
    "clarify_task": "确认需要补充的条件",
}
ARGUMENTS = {
    "generate_menu_plan": PlanParameters,
    "review_operations": ReviewArguments,
    "list_dishes": DishArguments,
    "get_dashboard": DashboardArguments,
    "get_menu_day": MenuDayArguments,
    "get_dish_recipe": DishRecipeArguments,
    "list_ingredients": IngredientArguments,
    "list_holidays": HolidayArguments,
    "get_current_plan": EmptyArguments,
    "check_data_readiness": PlanParameters,
    "clarify_task": ClarificationArguments,
}
DESCRIPTIONS = {
    "generate_menu_plan": "安排菜单或根据新人数、预算、排除菜品重算。diner_count 非空时直接使用，不再要求用户确认；为空时由后端按历史预测。只创建待确认方案，不发布。排除菜品必须先查询真实ID。",
    "review_operations": "查询最近若干天采集记录，按系统异常标记、同餐次盐量偏离、剩餐比例和数据覆盖情况生成可核查事实。",
    "list_dishes": "查询在用菜品真实ID、名称、类别与配方版本。换菜前用于解析名称，最多返回100道。",
    "get_dashboard": "只读查看最近若干天的管理看板：油盐糖趋势、人均摄入与推荐值、营养达标率、剩餐与浪费率。days 取 1–90，默认 14。所有数字来自看板接口，不允许自己估算。",
    "get_menu_day": "只读查看某天某一餐实际供应的菜品、份数、剩餐与每道菜单份营养。营养优先抽样实测，其次当日校准，最后标准配方理论值。on_date 不填表示今天；meal_type 用 BREAKFAST/LUNCH/DINNER 或 早餐/午餐/晚餐。",
    "get_dish_recipe": "只读查询一道菜的配方：每份食材与调味料用量、单价、可食部覆盖值，以及菜品单份营养。菜名有歧义时会返回候选，必须先问用户要哪一道，不能猜。",
    "list_ingredients": "只读查询食材营养。返回每100克可食部的能量、蛋白质、脂肪、碳水、钠，以及可食部比例、单价（元/公斤市品）、数据来源与版本。",
    "list_holidays": "只读查询某年的法定节假日与调休上班安排，可按月份过滤。周末不在日历表中；该表只含放假与调休两类特殊日期。",
    "get_current_plan": "读取最近一次方案、约束、营养差距和采购金额，用于解释、对比或继续调整。",
    "check_data_readiness": "只读检查指定日期/餐次/排除条件的配方、单价、营养缺项、类别和历史准备情况。生成前先检查，指出来源与下一步；不能把检查通过当作真实性认证。",
    "clarify_task": "用户要求缺失、含糊、互相矛盾或不支持时，停止计算并问一个明确问题，可提供最多4个候选回复。候选不能被当作用户已同意；禁止用此工具伪装发布/付款/管理员授权。",
}

MEAL_ALIASES = {"早餐": "BREAKFAST", "午餐": "LUNCH", "晚餐": "DINNER"}
NUTRIENT_KEYS = ("energy_kcal", "protein_g", "fat_g", "carb_g", "sodium_mg")
VALUE_TYPE_LABELS = {
    "SAMPLED": "抽样实测",
    "CALIBRATED": "当日校准",
    "THEORETICAL": "标准配方理论值",
}


def percent(value: str | None) -> str | None:
    """把接口的 0–1 小数换成对话里不容易读错的百分数。"""
    return None if value is None else f"{Decimal(value) * 100:.1f}%"


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
        if name == "get_dashboard":
            return await self.dashboard(parsed.days)
        if name == "get_menu_day":
            return await self.menu_day(parsed.on_date, parsed.meal_type)
        if name == "get_dish_recipe":
            return await self.dish_recipe(parsed.keyword)
        if name == "list_ingredients":
            return await self.ingredients(parsed.keyword)
        if name == "list_holidays":
            return await self.holidays(parsed.year, parsed.month)
        if name == "review_operations":
            return await self.review(parsed.days)
        raise AgentError("助手请求了未开放的工具", code="unknown_tool")

    async def dashboard(self, days: int) -> dict:
        """看板五项一次取回，只保留可读结论需要的字段。

        看板页面上的图表不经过模型；这里服务的是「帮我看一下最近几天怎么样」
        这类问题，因此趋势只保留最近 14 个点，避免 90 天查询把上下文撑满。
        """
        summary, trends, per_capita, compliance, waste = await asyncio.gather(
            self.business.request("GET", "dashboard/summary", params={"days": days}),
            self.business.request("GET", "dashboard/trends", params={"days": days}),
            self.business.request("GET", "dashboard/per-capita", params={"days": days}),
            self.business.request("GET", "dashboard/compliance", params={"days": days}),
            self.business.request("GET", "dashboard/waste", params={"days": days}),
        )
        points = trends.get("points", [])
        shown = points[-14:]
        comparisons = [
            {
                key: row.get(key)
                for key in (
                    "label",
                    "unit",
                    "target_min",
                    "target_max",
                    "actual",
                    "status",
                    "source",
                )
            }
            for row in per_capita.get("comparisons", [])
        ]
        latest_waste = waste.get("points", [])[-1] if waste.get("points") else None
        recorded_compliance = [
            row
            for row in compliance.get("points", [])
            if any(item.get("actual") is not None for item in row.get("items", []))
        ]
        last_compliance = recorded_compliance[-1] if recorded_compliance else None
        return {
            "days": days,
            "start": summary.get("start"),
            "end": summary.get("end"),
            "summary": {
                key: summary.get(key)
                for key in (
                    "days_with_records",
                    "avg_diner_count",
                    "avg_salt_per_capita_g",
                    "avg_oil_per_capita_g",
                    "avg_added_sugar_per_capita_g",
                    "avg_waste_ratio",
                    "avg_dish_variety",
                )
            },
            "trend": [
                {
                    key: row.get(key)
                    for key in (
                        "date",
                        "diner_count",
                        "oil_per_capita_g",
                        "salt_per_capita_g",
                        "sugar_per_capita_g",
                    )
                }
                for row in shown
            ],
            "trend_truncated": len(points) > len(shown),
            "targets": trends.get("targets", []),
            "per_capita": {
                "latest_date": per_capita.get("latest_date"),
                "latest": per_capita.get("latest", []),
                "average": per_capita.get("average", []),
                "comparisons": comparisons,
            },
            "compliance": {
                "overall_rate_percent": percent(compliance.get("overall_rate")),
                "last_recorded_date": last_compliance.get("date") if last_compliance else None,
                "last_recorded_rate_percent": percent(last_compliance.get("rate"))
                if last_compliance
                else None,
            },
            "waste": {
                "average_ratio": waste.get("average_ratio"),
                "latest": latest_waste,
            },
            "basis_note": per_capita.get("basis_note"),
            "note": "数值来自管理端看板接口；最近一天可能尚未录采集，达标率与人均值应结合「有记录天数」阅读。",
        }

    async def menu_day(self, on_date, meal_type: str) -> dict:
        """某天某餐的供应事实 + 每道菜单份营养。"""
        target = on_date or datetime.now(ZoneInfo("Asia/Shanghai")).date()
        meal = MEAL_ALIASES.get(meal_type, meal_type)
        sheet = await self.business.request(
            "GET", f"collection/logs/{target}", params={"meal_type": meal}
        )
        selected = [row for row in sheet.get("dishes", []) if row.get("selected")][:12]
        comparisons = await asyncio.gather(
            *[
                self.business.request(
                    "GET",
                    "calibration/comparison",
                    params={
                        "dish_id": row["dish_id"],
                        "on_date": str(target),
                        "meal_type": meal,
                    },
                )
                for row in selected
            ]
        )
        dishes = []
        for row, comparison in zip(selected, comparisons, strict=True):
            chosen, basis = None, None
            for value_type in ("SAMPLED", "CALIBRATED", "THEORETICAL"):
                if comparison.get(value_type.lower()):
                    chosen, basis = comparison[value_type.lower()], value_type
                    break
            nutrients = (
                {key: chosen.get(key) for key in NUTRIENT_KEYS}
                if chosen
                else {
                    "energy_kcal": row.get("energy_kcal"),
                    "protein_g": None,
                    "fat_g": None,
                    "carb_g": None,
                    "sodium_mg": None,
                }
            )
            dishes.append(
                {
                    "dish_id": row["dish_id"],
                    "name": row["name"],
                    "category_label": row.get("category_label"),
                    "cooking_method_label": row.get("cooking_method_label"),
                    "servings_produced": row.get("servings_produced"),
                    "leftover_ratio": row.get("leftover_ratio"),
                    "nutrients": nutrients,
                    "nutrition_basis": VALUE_TYPE_LABELS.get(basis, row.get("nutrition_source")),
                }
            )
        return {
            "date": str(target),
            "meal_type": meal,
            "meal_type_label": sheet.get("meal_type_label"),
            "saved": sheet.get("saved"),
            "submitted_at": sheet.get("submitted_at"),
            "diner_count": sheet.get("diner_count"),
            "oil_total_g": sheet.get("oil_total_g"),
            "salt_total_g": sheet.get("salt_total_g"),
            "sugar_total_g": sheet.get("sugar_total_g"),
            "leftover_weight_g": sheet.get("leftover_weight_g"),
            "anomaly_flags": [flag.get("label") for flag in sheet.get("anomaly_flags", [])],
            "menu_confirmed": sheet.get("menu_confirmed"),
            "warning": sheet.get("warning"),
            "selected_count": len(dishes),
            "dishes": dishes,
            "note": "营养为单份可食部；优先抽样实测，其次当日校准，最后标准配方理论值。油盐糖是这一餐的投料总量。",
        }

    async def dish_recipe(self, keyword: str) -> dict:
        """先按菜名解析唯一菜品，再读完整配方。名称有歧义时不猜。"""
        term = keyword.strip()
        result = await self.business.request(
            "GET", "dishes", params={"keyword": term, "page_size": 20}
        )
        items = result.get("items", [])
        exact = [row for row in items if row.get("name") == term]
        if len(exact) == 1:
            target = exact[0]
        elif len(items) == 1:
            target = items[0]
        elif len(items) > 1:
            return {
                "ambiguous": True,
                "keyword": term,
                "message": f"「{term}」命中多道菜，请让用户给出完整菜名，不能替用户选择。",
                "candidates": [
                    {
                        key: row.get(key)
                        for key in ("id", "name", "category_label", "cooking_method_label")
                    }
                    for row in items[:8]
                ],
            }
        else:
            return {
                "found": False,
                "keyword": term,
                "message": f"没有找到名称包含「{term}」的在用菜品。",
            }
        detail = await self.business.request("GET", f"dishes/{target['id']}")
        recipe = detail.get("recipe", {})
        nutrition = detail.get("nutrition") or {}
        return {
            "id": detail.get("id"),
            "name": detail.get("name"),
            "category_label": detail.get("category_label"),
            "cooking_method_label": detail.get("cooking_method_label"),
            "standard_serving_g": detail.get("standard_serving_g"),
            "recipe_version": detail.get("recipe_version"),
            "nutrition": {
                "date": nutrition.get("date"),
                "value_type": nutrition.get("value_type"),
                "energy_kcal": nutrition.get("energy_kcal"),
                "protein_g": nutrition.get("protein_g"),
                "fat_g": nutrition.get("fat_g"),
                "carb_g": nutrition.get("carb_g"),
                "sodium_mg": nutrition.get("sodium_mg"),
            },
            "ingredients": [
                {
                    key: row.get(key)
                    for key in (
                        "ingredient_name",
                        "quantity_per_serving_g",
                        "edible_ratio_override",
                        "unit_price",
                    )
                }
                for row in recipe.get("ingredients", [])
            ],
            "seasonings": [
                {
                    key: row.get(key)
                    for key in ("seasoning_name", "quantity_per_serving_g", "unit_price")
                }
                for row in recipe.get("seasonings", [])
            ],
            "note": "食材与调味料用量均为每份；单价为元/公斤市品；营养为该菜品当前单份结果。",
        }

    async def ingredients(self, keyword: str) -> dict:
        result = await self.business.request(
            "GET", "ingredients", params={"keyword": keyword.strip(), "page_size": 10}
        )
        items = result.get("items", [])
        return {
            "keyword": keyword,
            "total": result.get("total", 0),
            "truncated": result.get("total", 0) > len(items),
            "items": [
                {
                    key: row.get(key)
                    for key in (
                        "id",
                        "name",
                        "category_label",
                        "energy_kcal",
                        "protein_g",
                        "fat_g",
                        "carb_g",
                        "sodium_mg",
                        "edible_ratio",
                        "unit_price",
                        "data_source",
                        "source_version",
                        "note",
                    )
                }
                for row in items
            ],
            "note": "营养为每100克可食部；单价为元/公斤市品；来源与版本按条目保留。没有单价时不要估算金额。",
        }

    async def holidays(self, year: int | None, month: int | None) -> dict:
        target_year = year or datetime.now(ZoneInfo("Asia/Shanghai")).year
        result = await self.business.request(
            "GET", "forecast/holidays", params={"year": target_year}
        )
        items = [
            row
            for row in result.get("items", [])
            if month is None or int(str(row["date"])[5:7]) == month
        ]
        return {
            "year": target_year,
            "month": month,
            "total": len(items),
            "items": [
                {key: row.get(key) for key in ("date", "name", "kind", "kind_label", "is_verified")}
                for row in items
            ],
            "unverified_count": sum(1 for row in items if not row.get("is_verified")),
            "source_note": items[0].get("source_note") if items else None,
            "note": (
                "只列法定节假日与调休上班；普通周末不在这张表里。"
                if items
                else "这一年（或这个月）没有已录入的节假日或调休记录；普通周末不在这张表里。"
            ),
        }

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

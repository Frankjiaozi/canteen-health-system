"""有限任务识别：逐字段解析，歧义时保留已明确条件，等待用户补充。"""

import re
from datetime import date, datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from .errors import TaskClarification
from .schemas import PendingTask, PlanParameters

MEALS = {"早餐": "BREAKFAST", "午餐": "LUNCH", "晚餐": "DINNER"}
NEGATIVE = ("换掉", "替换", "排除", "不要", "去掉", "不做")
GENERATION_PROHIBITION = (
    r"(?:不要|不用|先别|先不|取消|暂不)(?:再|继续|重新)?(?:安排|生成|重算)(?:菜单|方案|采购单)?"
)


def generation_forbidden(content: str) -> bool:
    return bool(re.search(GENERATION_PROHIBITION, content))


def without_generation_prohibition(content: str) -> str:
    return re.sub(GENERATION_PROHIBITION + r"(?=$|[，,。；;！!])", "", content)


def is_cancel(content: str) -> bool:
    return content.strip().rstrip("。！!") in {
        "取消补充",
        "取消这次任务",
        "取消澄清",
        "先停一下",
        "停止任务",
    } or (
        generation_forbidden(content)
        and not re.search(r"检查|体检|核查|查询|查看|列出|解释|分析|对比|比较", content)
    )


def intent(content: str) -> str:
    content = without_generation_prohibition(content)
    if any(
        word in content for word in ("数据体检", "数据准备", "检查数据", "数据够不够", "缺什么数据")
    ):
        return "check_data_readiness"
    if any(word in content for word in ("为什么", "依据", "解释", "怎么算", "对比", "比较")):
        return "get_current_plan"
    if any(word in content for word in ("安排", "生成", "重算", "换掉", "排除")):
        return "generate_menu_plan"
    if any(
        word in content for word in ("核查", "异常", "分析", "近一周", "剩餐", "浪费", "周报")
    ) or re.search(r"(?:近|最近)\s*\d+\s*天", content):
        return "review_operations"
    if any(word in content for word in ("菜单", "换", "预算", "人", "不要", "去掉", *MEALS)):
        return "generate_menu_plan"
    return "help"


def choice(label: str, content: str) -> dict:
    return {"label": label, "content": content}


def parse_date(content: str, data: dict, today: date):
    values: set[date] = set()
    remaining = content
    for label, offset in (("大后天", 3), ("今天", 0), ("明天", 1), ("明日", 1), ("后天", 2)):
        if label in remaining:
            values.add(today + timedelta(days=offset))
            remaining = remaining.replace(label, "")
    for value in re.findall(r"20\d{2}-\d{1,2}-\d{1,2}", content):
        try:
            values.add(date(*map(int, value.split("-"))))
        except ValueError:
            raise TaskClarification("这个日期不存在，请核对供餐日期。", "on_date") from None
    for modifier, label in re.findall(r"(下下|下|本|这)?(?:周|星期)([一二三四五六日天])", content):
        distance = min("一二三四五六日天".index(label), 6) - today.weekday()
        if modifier in {"下", "下下"}:
            distance += 7 if modifier == "下" else 14
        elif modifier not in {"本", "这"}:
            distance %= 7
        values.add(today + timedelta(days=distance))
    if len(values) > 1:
        raise TaskClarification(
            "这条消息有多个供餐日期，请先选择本次要安排的一天。",
            "on_date",
            [choice(str(value), f"{value}，安排菜单与采购") for value in sorted(values)[:4]],
        )
    if any(word in content for word in ("周菜单", "一周菜单", "多天菜单")) or (
        not values and re.search(r"下周|本周|下星期|\d+月\d+[日号]", content)
    ):
        raise TaskClarification("每次先安排一天的一餐，请选择具体日期或星期几。", "on_date")
    if values:
        value = next(iter(values))
        if value < today:
            raise TaskClarification(
                "安排菜单请选今天或之后；历史数据可用记录核查。",
                "on_date",
                [choice("安排明天", "明天安排菜单与采购")],
            )
        data["on_date"] = str(value)


def parse_meal(content: str, data: dict):
    meals = [label for label in MEALS if label in content]
    if len(meals) > 1:
        raise TaskClarification(
            "本次先安排哪个餐次？其他餐次可另建任务。",
            "meal_type",
            [choice(label, f"安排{label}菜单与采购") for label in meals],
        )
    if meals:
        data["meal_type"] = MEALS[meals[0]]


def parse_diners(content: str, data: dict):
    if re.search(r"[零一二两三四五六七八九十百千万]+\s*人", content):
        raise TaskClarification("规则模式请用阿拉伯数字写人数，例如 1000 人。", "diner_count")
    if re.search(r"(?:\d+\.\d+|[-－]\s*\d+)\s*(?:人次|人)", content):
        raise TaskClarification("就餐人次必须是正整数，请核对人数。", "diner_count")
    people = re.findall(r"(\d[\d,]*)\s*(?:人次|人)", content)
    if re.search(r"\d+\s*(?:~|～|至|到)\s*\d+\s*人", content) or (
        len(people) > 1
        and (
            re.search("或|或者", content)
            or not re.search(r"(?:改|调|增|降)(?:成|为|到|至)?", content)
        )
    ):
        raise TaskClarification(
            "请先选定这餐的具体就餐人次，不使用范围或多个备选人数。",
            "diner_count",
            [
                choice(f"{number} 人", f"改成{number}人，安排菜单与采购")
                for number in list(dict.fromkeys(people))[:4]
            ],
        )
    if people:
        value = int(people[-1].replace(",", ""))
        if not 1 <= value <= 100000:
            raise TaskClarification("就餐人次应为 1–100000 的整数，请重新指定。", "diner_count")
        data["diner_count"] = value


def parse_budget(content: str, data: dict):
    if re.search(
        r"\d+(?:\.\d+)?\s*(?:元)?\s*(?:至|到|~|～)\s*\d+(?:\.\d+)?\s*元", content
    ) or re.search(
        r"(?:预算|每人|人均)[^\d，。；\n]{0,6}\d+(?:\.\d+)?\s*(?:至|到|~|～)\s*\d+(?:\.\d+)?",
        content,
    ):
        raise TaskClarification("预算暂不接受范围，请指定本次每人的具体金额。", "budget_per_person")
    if re.search(r"[零一二两三四五六七八九十百千万]+\s*元", content):
        raise TaskClarification(
            "规则模式请用阿拉伯数字写预算，例如每人 8 元。", "budget_per_person"
        )
    if re.search(r"(?:预算|每人|人均)[^，。；\n]{0,8}[-－]\s*\d", content):
        raise TaskClarification("预算必须大于零，请核对金额。", "budget_per_person")
    if re.search(r"\d+\.\d{3,}\s*元", content):
        raise TaskClarification("每人预算最多保留两位小数，请核对金额。", "budget_per_person")
    matches = list(
        re.finditer(r"(?:每人|人均|预算)[^\d，。；]{0,6}(\d+(?:\.\d+)?)\s*(?:元)?", content)
    )
    changed = re.search(r"(?:改|调|降|升)(?:成|为|到|至)\s*(\d+(?:\.\d+)?)\s*元", content)
    relative = re.search(
        r"(?:预算|每人|人均)[^，。；]{0,5}(减少|降低|增加|提高|少|多)\s*(\d+(?:\.\d+)?)\s*元",
        content,
    )
    if matches or changed:
        if len(re.findall(r"\d+(?:\.\d+)?\s*元", content)) > 1 and re.search("或|或者", content):
            raise TaskClarification("预算有多个备选值，请指定本次每人预算。", "budget_per_person")
        amount = Decimal(changed.group(1) if changed else matches[-1].group(1))
        if relative:
            amount = Decimal(data["budget_per_person"]) + Decimal(relative.group(2)) * (
                1 if relative.group(1) in {"增加", "提高", "多"} else -1
            )
        elif (
            "每人" not in content
            and "人均" not in content
            and re.search(r"总预算|预算总额", content)
        ):
            if not data["diner_count"]:
                raise TaskClarification(
                    "请先指定就餐人数，再将总预算换算为每人预算。", "diner_count"
                )
            amount = (amount / Decimal(data["diner_count"])).quantize(
                Decimal("0.01"), rounding=ROUND_DOWN
            )
        if amount <= 0 or amount > 1000 or amount.as_tuple().exponent < -2:
            raise TaskClarification(
                "每人预算应大于零、不超过 1000 元，最多两位小数。", "budget_per_person"
            )
        data["budget_per_person"] = str(amount)
    elif "预算" in content and any(
        word in content for word in ("低一点", "少一点", "降一点", "提高", "减少", "降低", "多一点")
    ):
        current = Decimal(data["budget_per_person"])
        smaller = max(Decimal("0.01"), current - 1)
        raise TaskClarification(
            "请指定新的每人预算，规则模式不能判断‘少一点’是多少。",
            "budget_per_person",
            [
                choice(f"每人 {smaller} 元", f"预算每人{smaller}元，安排菜单与采购"),
                choice(f"仍用每人 {current} 元", f"预算每人{current}元，安排菜单与采购"),
            ],
        )


def parse_exclusions(content: str, data: dict, dishes: list[dict]):
    content = without_generation_prohibition(content)
    if any(word in content for word in ("清空排除", "恢复全部菜品")) or (
        "不再排除" in content and not any(row["name"] in content for row in dishes)
    ):
        data["excluded_dish_ids"] = []
        for phrase in ("清空排除", "恢复全部菜品", "不再排除"):
            content = content.replace(phrase, "")
    excluded = set(data["excluded_dish_ids"])
    changed = False
    for clause in re.split(r"[，,。；;\n]|但是|但|而且|同时", content):
        restoring = any(word in clause for word in ("恢复", "不再排除", "不要排除", "不要换"))
        replacing = any(word in clause for word in NEGATIVE) and not restoring
        if not replacing and not restoring:
            continue
        changed = True
        if replacing and any(word in clause for word in ("保留", "留下", "照旧", "不替换")):
            raise TaskClarification(
                "请把要排除的菜名单独写一句，保留的菜无需重复；也可以直接在条件面板选择。",
                "excluded_dish_ids",
            )
        matched, remaining = [], clause
        for item in sorted(dishes, key=lambda row: len(row["name"]), reverse=True):
            if item["name"] in remaining:
                matched.append(item["id"])
                remaining = remaining.replace(item["name"], " ")
        if not matched:
            raise TaskClarification(
                "请写出要排除或恢复的完整菜名，也可以用条件面板选择；规则模式无法理解泛指替换。",
                "excluded_dish_ids",
            )
        if restoring:
            excluded -= set(matched)
        else:
            excluded |= set(matched)
    if changed:
        data["excluded_dish_ids"] = sorted(excluded)


class ParsedParameters(dict):
    """记录显式指定的字段，包括与原值相同的回答。"""

    def __init__(self, values):
        super().__init__(values)
        self.touched: set[str] = set()

    def __setitem__(self, key, value):
        self.touched.add(key)
        super().__setitem__(key, value)


def remaining_questions(pending: PendingTask, parameters: PlanParameters) -> list[dict]:
    records = [row.model_dump(mode="json") for row in pending.questions] or [
        {
            "field": pending.field,
            "message": "请补充尚未确定的条件，或取消后重新安排。",
            "choices": [],
        }
    ]
    return [
        row
        for row in records
        if row["field"] not in PlanParameters.model_fields
        or getattr(parameters, row["field"]) == getattr(pending.parameters, row["field"])
    ]


def parameters_from_text(
    content: str,
    base: PlanParameters,
    dishes: list[dict],
    pending: list[dict] | None = None,
    *,
    changed_fields: set[str] | None = None,
    allow_multiple_intents: bool = False,
) -> PlanParameters:
    data = ParsedParameters(base.model_dump(mode="json"))
    questions = {
        row["field"]: TaskClarification(row["message"], row["field"], row["choices"])
        for row in pending or []
    }
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    for parser, args in (
        (parse_date, (today,)),
        (parse_meal, ()),
        (parse_diners, ()),
        (parse_budget, ()),
        (parse_exclusions, (dishes,)),
    ):
        try:
            parser(content, data, *args)
            for field in data.touched:
                questions.pop(field, None)
        except TaskClarification as question:
            questions[question.field] = question
    if re.search(r"过敏|忌口|不辣|少油|少盐|高蛋白|减脂|清真|库存|素食", content):
        questions["conditions"] = TaskClarification(
            "当前工具还不能验证这项特殊膳食或库存约束。请人工核对并明确排除具体菜品；仅凭菜名不能保证满足要求。",
            "conditions",
            [choice("只按当前条件安排", "只按当前任务条件安排菜单与采购")],
        )
    elif "只按当前任务条件安排" in content:
        questions.pop("conditions", None)
    if (
        not allow_multiple_intents
        and re.search(r"核查|分析|周报", content)
        and re.search(r"安排|生成|重算", content)
    ):
        questions["intent"] = TaskClarification(
            "这条消息同时包含记录核查和菜单安排。规则模式先选一个任务；模型模式可按工具分步处理。",
            "intent",
            [
                choice("先核查近7天", "核查最近7天供应记录"),
                choice("按当前条件安排", "按当前任务条件安排菜单与采购"),
            ],
        )
    elif intent(content) in {"review_operations", "generate_menu_plan", "check_data_readiness"}:
        questions.pop("intent", None)
    if changed_fields is not None:
        changed_fields.update(data.touched)
    if questions:
        records = [
            {"field": row.field, "message": row.message, "choices": row.choices}
            for row in questions.values()
        ]
        question = next(iter(questions.values()))
        question.questions = records
        if len(questions) > 1:
            question.message = (
                "先补充一项："
                + question.message
                + "\n其余待确认："
                + "；".join(row.message for row in list(questions.values())[1:])
            )
        question.parameters = data
        raise question
    try:
        return PlanParameters.model_validate(data)
    except ValidationError:
        raise TaskClarification("请核对日期、餐次、人数和每人预算后再安排。") from None


def followup(content: str, field: str) -> str:
    """对澄清问题的简短回答转为明确任务；完整新任务保持原样。"""
    text = content.strip().rstrip("。！!")
    if field == "budget_per_person" and re.fullmatch(r"\d+(?:\.\d+)?\s*元?", text):
        return f"每人预算{text.removesuffix('元').strip()}元，安排菜单与采购"
    if field == "diner_count" and re.fullmatch(r"\d[\d,]*\s*(?:人次|人)?", text):
        value = re.match(r"\d[\d,]*", text).group()
        return f"{value}人，安排菜单与采购"
    if field == "meal_type" and text in MEALS:
        return f"安排{text}菜单与采购"
    if field == "on_date" and re.fullmatch(
        r"今天|明天|明日|后天|大后天|20\d{2}-\d{1,2}-\d{1,2}|(?:下下|下|本|这)?(?:周|星期)[一二三四五六日天]",
        text,
    ):
        return f"{text}安排菜单与采购"
    return content

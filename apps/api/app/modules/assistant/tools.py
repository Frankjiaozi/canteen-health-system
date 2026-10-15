"""助手能用的工具：任务级、只读，直接调各业务域的 service。

三条约定：

1. **任务级**，不是「把 REST 接口原样搬过来」。「查这道菜的配方和单份营养」是一个工具，
   不是「查菜品详情 + 查营养结果」两个——模型少选一次，就少一次选错。
2. **只读**。阶段一不给任何写操作：助手写错东西会进历史、影响预测与公开大屏，
   那要有确认与审计才敢开。`get_tools()` 里全是查询，测试里有一条专门盯着这件事。
3. **不编数据**。工具返回的是库里的真实值，连「这个值来自哪一层」一起给出来，
   模型据此作答即可，不需要（也不允许）自己估一个营养值。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import BusinessRuleError
from app.modules.analytics import service as analytics_service
from app.modules.collection import service as collection_service
from app.modules.dish import service as dish_service
from app.modules.ingredient import service as ingredient_service
from app.shared.enums import DishCategory, IngredientCategory, MealType, UserRole
from app.shared.nutrition_values import VALUE_TYPE_DESCRIPTIONS

#: 一次最多回几条：助手是给人看结论的，不是导数据用的。要全量请去对应页面。
MAX_ROWS = 20


def today() -> date:
    return datetime.now(get_settings().timezone).date()


def _num(value: Decimal | None) -> str | None:
    """小数按人看得懂的方式给：去掉无意义的尾零。"""
    if value is None:
        return None
    return str(value.normalize()) if value == value.to_integral_value() else str(value)


def _enum_arg(enum_type: Any, value: str | None, label: str) -> Any | None:
    if value is None or value == "":
        return None
    try:
        return enum_type(value)
    except ValueError as error:
        allowed = "、".join(f"{member.value}（{member.label}）" for member in enum_type)
        raise BusinessRuleError(f"{label}取值无效，只能是：{allowed}") from error


def _meal_arg(value: str | None) -> MealType:
    meal = _enum_arg(MealType, value or MealType.LUNCH.value, "餐次")
    assert meal is not None
    return meal


def _date_arg(value: str | None) -> date:
    """模型给的日期字符串。解析不了就报错说清楚，而不是猜一个日子。"""
    if not value:
        return today()
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise BusinessRuleError(
            f"日期格式不对：{value}。要写成 YYYY-MM-DD，例如 {today().isoformat()}"
        ) from error


# ---------------------------------------------------------------------------
# 工具实现
# ---------------------------------------------------------------------------
def search_ingredients(
    session: Session, *, keyword: str | None = None, category: str | None = None, limit: int = 10
) -> dict[str, Any]:
    """按关键词/类别查食材库，返回营养（每 100 克可食部）与单价。"""
    page = ingredient_service.list_ingredients(
        session,
        keyword=keyword or None,
        category=_enum_arg(IngredientCategory, category, "食材类别"),
        page=1,
        page_size=min(max(limit, 1), MAX_ROWS),
    )
    return {
        "total": page.total,
        "items": [
            {
                "名称": row.name,
                "类别": row.category_label,
                "每100克可食部": {
                    "能量_千卡": _num(row.energy_kcal),
                    "蛋白质_克": _num(row.protein_g),
                    "脂肪_克": _num(row.fat_g),
                    "碳水_克": _num(row.carb_g),
                    "钠_毫克": _num(row.sodium_mg),
                },
                "可食部比例": _num(row.edible_ratio),
                "单价_元每公斤市品": _num(row.unit_price),
                "数据来源": row.data_source,
                "来源版本": row.source_version,
                "备注": row.note,
            }
            for row in page.items
        ],
    }


def search_dishes(
    session: Session, *, keyword: str | None = None, category: str | None = None, limit: int = 10
) -> dict[str, Any]:
    """按关键词/类别查菜品，返回单份营养与营养取自哪一层。"""
    page = dish_service.list_dishes(
        session,
        keyword=keyword or None,
        category=_enum_arg(DishCategory, category, "菜品类别"),
        page=1,
        page_size=min(max(limit, 1), MAX_ROWS),
    )
    return {
        "total": page.total,
        "items": [
            {
                "菜品": row.name,
                "类别": row.category_label,
                "做法": row.cooking_method_label,
                "标准份量_克": _num(row.standard_serving_g),
                "单份营养": None
                if row.nutrition is None
                else row.nutrition.model_dump(mode="json"),
            }
            for row in page.items
        ],
    }


def get_dish_recipe(session: Session, *, dish_name: str) -> dict[str, Any]:
    """查一道菜的配方（食材与调味料用量）与单份营养，便于回答「这道菜怎么做」。"""
    found = dish_service.list_dishes(session, keyword=dish_name, page=1, page_size=MAX_ROWS)
    exact = [row for row in found.items if row.name == dish_name] or list(found.items)
    if not exact:
        raise BusinessRuleError(f"菜品库里没有找到「{dish_name}」，换个关键词试试")
    detail = dish_service.get_dish_detail(session, exact[0].id)
    recipe = detail.recipe
    return {
        "菜品": detail.name,
        "类别": detail.category_label,
        "做法": detail.cooking_method_label,
        "标准份量_克": _num(detail.standard_serving_g),
        "单份营养": None if detail.nutrition is None else detail.nutrition.model_dump(mode="json"),
        "配方食材": None
        if recipe is None
        else [item.model_dump(mode="json") for item in recipe.ingredients],
        "配方调味料": None
        if recipe is None
        else [item.model_dump(mode="json") for item in recipe.seasonings],
        "提示": "营养值来自库里已算好的结果；缺项与数值口径见 nutrition 字段",
    }


def get_menu_day(
    session: Session, *, on_date: str | None = None, meal_type: str | None = None
) -> dict[str, Any]:
    """查某一天某一餐供应了哪些菜、哪些是计划、单份营养如何。"""
    target = _date_arg(on_date)
    meal = _meal_arg(meal_type)
    sheet = collection_service.build_sheet(session, on_date=target, meal_type=meal)
    # 菜单日上的菜就是这一餐的菜：还没录采集时它是**计划**，录过之后是**实际供应**。
    # 两种都要列出来——问「今天吃什么」的人不会区分这两个词。
    served = [row for row in sheet.dishes if row.selected]
    return {
        "日期": target.isoformat(),
        "餐次": sheet.meal_type_label,
        "菜单是否已确认": sheet.menu_confirmed,
        "采集是否已录": sheet.saved,
        "就餐人次": sheet.diner_count,
        "当日油盐糖_克": {
            "食用油": sheet.oil_total_g,
            "食盐": sheet.salt_total_g,
            "添加糖": sheet.sugar_total_g,
        },
        "供应的菜": [
            {
                "菜品": row.name,
                "类别": row.category_label,
                "是计划还是实际": "计划（还没录采集）" if row.is_planned else "实际供应",
                "计划份数": row.planned_servings,
                "实际出餐份数": row.servings_produced,
                "单份能量_千卡": row.energy_kcal,
                "营养取自": row.nutrition_source,
            }
            for row in served
        ],
        "提示": sheet.warning
        or (
            "「供应的菜」为空只说明这一天还没有确认菜单，不代表没供餐"
            if not served
            else "计划份数来自预测、实际出餐份数来自采集；两者都在时可以对账"
        ),
    }


def get_dashboard(session: Session, *, days: int = 14) -> dict[str, Any]:
    """看板四类指标：油盐糖趋势、人均摄入、达标率、剩餐浪费率。"""
    window = min(max(days, 1), 90)
    summary = analytics_service.build_summary(session, days=window)
    compliance = analytics_service.build_compliance(session, days=window)
    waste = analytics_service.build_waste(session, days=window)
    per_capita = analytics_service.build_per_capita(session, days=window)
    return {
        "统计天数": window,
        "汇总": summary.model_dump(mode="json"),
        "达标率": compliance.model_dump(mode="json"),
        "人均摄入": per_capita.model_dump(mode="json"),
        "剩餐与浪费": waste.model_dump(mode="json"),
        "口径提示": "达标率与对照基准取自《中国居民膳食指南（2022）》的量化指标；"
        "人均摄入是人均供给，不等于每个人实际吃了多少",
    }


def list_recent_collections(session: Session, *, days: int = 7) -> dict[str, Any]:
    """最近几天录了哪些采集：人次、油盐糖总量、菜品数、浪费率。"""
    window = min(max(days, 1), 30)
    end = today()
    page = collection_service.list_logs(
        session,
        page=1,
        page_size=min(window, MAX_ROWS),
        start=end - timedelta(days=window),
        end=end,
    )
    return {
        "统计天数": window,
        "total": page.total,
        "items": [
            {
                "日期": row.date.isoformat(),
                "餐次": row.meal_type_label,
                "就餐人次": row.diner_count,
                "食用油_克": row.oil_total_g,
                "食盐_克": row.salt_total_g,
                "添加糖_克": row.sugar_total_g,
                "菜品数": row.dish_count,
                "浪费率": row.waste_ratio,
                "异常": [flag.label for flag in row.anomaly_flags],
            }
            for row in page.items
        ],
    }


# ---------------------------------------------------------------------------
# 注册表
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    label: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., dict[str, Any]]
    read_only: bool = True


def _schema(properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "additionalProperties": False}


TOOLS: tuple[Tool, ...] = (
    Tool(
        name="search_ingredients",
        label="查食材库",
        description=(
            "按关键词或类别查食材，返回每 100 克可食部的营养、可食部比例、单价与数据来源。"
            "问「某食材营养是多少/多少钱」「库里有没有某样食材」用它。"
        ),
        parameters=_schema(
            {
                "keyword": {"type": "string", "description": "名称关键词，例如「土豆」"},
                "category": {
                    "type": "string",
                    "description": "食材类别代码，例如 GRAIN / VEGETABLE / LIVESTOCK_POULTRY",
                },
                "limit": {"type": "integer", "description": "最多返回几条，默认 10"},
            }
        ),
        handler=search_ingredients,
    ),
    Tool(
        name="search_dishes",
        label="查菜品",
        description="按关键词或类别查菜品，返回做法、标准份量与单份营养。问「有哪些素菜」用它。",
        parameters=_schema(
            {
                "keyword": {"type": "string", "description": "菜名关键词"},
                "category": {
                    "type": "string",
                    "description": "菜品类别代码，例如 STAPLE / MEAT / HALF_MEAT / VEGETABLE / SOUP",
                },
                "limit": {"type": "integer", "description": "最多返回几条，默认 10"},
            }
        ),
        handler=search_dishes,
    ),
    Tool(
        name="get_dish_recipe",
        label="查菜品配方",
        description=(
            "查一道菜的完整配方（食材与调味料的单份用量）与单份营养。"
            "问「某道菜怎么做/用了什么料」用它。"
        ),
        parameters=_schema(
            {"dish_name": {"type": "string", "description": "菜名，例如「宫保鸡丁」"}}
        ),
        handler=get_dish_recipe,
    ),
    Tool(
        name="get_menu_day",
        label="查某天的菜单",
        description=(
            "查某一天某一餐供应了哪些菜、计划份数、实际出餐份数、单份营养，"
            "以及那一天是否已录采集。问「某天吃什么」「某天录了吗」用它。"
        ),
        parameters=_schema(
            {
                "on_date": {"type": "string", "description": "日期 YYYY-MM-DD，默认今天"},
                "meal_type": {"type": "string", "description": "餐次：BREAKFAST / LUNCH / DINNER"},
            }
        ),
        handler=get_menu_day,
    ),
    Tool(
        name="get_dashboard",
        label="看板指标",
        description=(
            "取最近若干天的关键指标：油盐糖用量、人均摄入与推荐值对比、营养达标率、"
            "剩餐量与浪费率。问「最近盐用超了没」「达标情况如何」用它。"
        ),
        parameters=_schema(
            {"days": {"type": "integer", "description": "统计最近几天，默认 14，最多 90"}}
        ),
        handler=get_dashboard,
    ),
    Tool(
        name="list_recent_collections",
        label="最近采集记录",
        description="列出最近几天的采集记录：人次、油盐糖总量、菜品数、浪费率与异常标记。",
        parameters=_schema(
            {"days": {"type": "integer", "description": "最近几天，默认 7，最多 30"}}
        ),
        handler=list_recent_collections,
    ),
)

TOOLS_BY_NAME: dict[str, Tool] = {tool.name: tool for tool in TOOLS}

#: 阶段一允许使用的角色。读操作对三个角色都开放：学校管理方本来就是只读观察者。
ALLOWED_ROLES: frozenset[UserRole] = frozenset(
    {UserRole.RECORDER, UserRole.CANTEEN_ADMIN, UserRole.SCHOOL_ADMIN}
)


def assert_read_only() -> None:
    """自查：注册表里不许出现写操作。

    阶段一的分界线就在这里——工具一旦能写，就必须先有确认与审计。
    把这条写成一个函数并由测试调用，是为了以后有人往里加工具时会被当场拦住。
    """
    offenders = [tool.name for tool in TOOLS if not tool.read_only]
    if offenders:
        raise AssertionError(f"阶段一只允许只读工具，发现写操作：{offenders}")
    write_verbs = ("create", "update", "delete", "save", "sync", "import", "generate", "decide")
    leaked = [
        tool.name for tool in TOOLS if any(tool.name.startswith(f"{verb}_") for verb in write_verbs)
    ]
    if leaked:
        raise AssertionError(f"工具名看起来像写操作：{leaked}")


def tool_payload() -> list[dict[str, Any]]:
    """给模型看的工具清单（OpenAI 的函数调用格式）。"""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
        for tool in TOOLS
    ]


def describe_value_types() -> dict[str, str]:
    """营养值「来自哪一层」的说法，交给模型解释时用。"""
    return {str(key): value for key, value in VALUE_TYPE_DESCRIPTIONS.items()}

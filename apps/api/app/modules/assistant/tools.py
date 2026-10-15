"""助手能用的工具：任务级，直接调各业务域的 service。

三条约定：

1. **任务级**，不是「把 REST 接口原样搬过来」。「查这道菜的配方和单份营养」是一个工具，
   不是「查菜品详情 + 查营养结果」两个——模型少选一次，就少一次选错。
2. **写操作必须过闸门**。写工具不直接执行：`preview()` 先把「打算写什么」整理成一份方案，
   由人点确认之后才用同一个 `payload` 调 `execute()`。这条不是靠提示词自律，
   而是这一层的结构决定的——写工具的 `execute` 只在确认路径上被调用，
   `assert_write_boundary()` 保证没有哪个工具能绕过它。
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
from app.modules.seasoning import service as seasoning_service
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
# 工具的结构（写工具的实现放在下面，注册表要引用它们）
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    label: str
    description: str
    parameters: dict[str, Any]
    #: 读工具：调用即查询。写工具：调用只生成方案，`handler` 不参与执行
    handler: Callable[..., dict[str, Any]]
    read_only: bool = True
    #: 写工具专用：把参数整理成一份给人看的方案 + 将要执行的参数
    build_draft: Callable[..., dict[str, Any]] | None = None
    #: 写工具专用：用户确认之后才执行
    execute: Callable[..., dict[str, Any]] | None = None


def _ingredient_by_exact_name(session: Session, name: str) -> Any | None:
    page = ingredient_service.list_ingredients(session, keyword=name, page=1, page_size=MAX_ROWS)
    return next((row for row in page.items if row.name == name), None)


def _seasoning_by_exact_name(session: Session, name: str) -> Any | None:
    page = seasoning_service.list_seasonings(session, keyword=name, page=1, page_size=MAX_ROWS)
    return next((row for row in page.items if row.name == name), None)


# ---------------------------------------------------------------------------
# 写工具：只出方案，确认后才执行
# ---------------------------------------------------------------------------
def create_ingredient_draft(
    session: Session,
    *,
    name: str,
    category: str,
    data_source: str,
    energy_kcal: str | None = None,
    protein_g: str | None = None,
    fat_g: str | None = None,
    carb_g: str | None = None,
    sodium_mg: str | None = None,
    edible_ratio: str | None = None,
    unit_price: str | None = None,
    source_version: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """把「新增食材」整理成一份待确认的方案（这一层不写库）。"""
    existing = _ingredient_by_exact_name(session, name)
    fields = {
        "名称": name,
        "类别": category,
        "能量_千卡每100克": energy_kcal,
        "蛋白质_克每100克": protein_g,
        "脂肪_克每100克": fat_g,
        "碳水_克每100克": carb_g,
        "钠_毫克每100克": sodium_mg,
        "可食部比例": edible_ratio,
        "单价_元每公斤市品": unit_price,
        "数据来源": data_source,
        "来源版本": source_version,
        "备注": note,
    }
    warnings: list[str] = []
    if existing is not None:
        warnings.append(f"食材库里已经有「{name}」，再建会撞唯一约束，请改用别的名字或去修改那一条")
    missing = [
        label
        for label, value in (
            ("能量", energy_kcal),
            ("蛋白质", protein_g),
            ("脂肪", fat_g),
            ("碳水", carb_g),
            ("钠", sodium_mg),
        )
        if not value
    ]
    if missing:
        warnings.append("这些成分留空（系统允许缺项，不会当成 0）：" + "、".join(missing))
    price = f"，单价 {unit_price} 元/公斤市品" if unit_price else ""
    return {
        "title": f"新增食材：{name}",
        "summary": f"在食材库新增「{name}」（{category}）{price}；数据来源：{data_source}",
        "preview": {"将新增": fields, "提示": warnings, "动作": "在食材库新增一条食材"},
        # 执行时原样用这份参数：页面上看到的就是要写进去的
        "payload": {
            "name": name,
            "category": category,
            "energy_kcal": energy_kcal,
            "protein_g": protein_g,
            "fat_g": fat_g,
            "carb_g": carb_g,
            "sodium_mg": sodium_mg,
            "edible_ratio": edible_ratio or "1.0",
            "unit_price": unit_price,
            "data_source": data_source,
            "source_version": source_version,
            "note": note,
        },
    }


def create_ingredient_execute(
    session: Session, payload: dict[str, Any], *, actor: Any
) -> dict[str, Any]:
    """确认之后真正写库。走的是食材域自己的 service，审计与校验与页面录入完全一致。"""
    from app.modules.ingredient.schemas import IngredientCreate

    created = ingredient_service.create_ingredient(
        session,
        IngredientCreate(**payload),
        actor_id=actor.id,
        actor_name=actor.display_name,
        audit_note="经「AI 助手」提议、由本人确认后创建",
    )
    return {"实体": "食材", "id": str(created.id), "名称": created.name}


def create_dish_draft(
    session: Session,
    *,
    name: str,
    category: str,
    cooking_method: str,
    standard_serving_g: str,
    servings_per_pot: str | None = None,
    allergens: list[str] | None = None,
    recipe_items: list[dict[str, Any]] | None = None,
    seasoning_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """把「新增菜品 + 配方」整理成一份待确认的方案，并把食材名解析成库里的条目。

    名字解析放在这里而不是执行时：**方案里要能看见「西红柿」到底对应库里哪一条**，
    对不上就当场说清楚，而不是等人点了确认再报错。
    """
    page = dish_service.list_dishes(session, keyword=name, page=1, page_size=MAX_ROWS)
    warnings: list[str] = []
    if any(row.name == name for row in page.items):
        warnings.append(f"菜品库里已经有「{name}」，再建会撞唯一约束")

    resolved: list[dict[str, Any]] = []
    payload_items: list[dict[str, Any]] = []
    for line in recipe_items or []:
        ingredient_name = str(line.get("ingredient_name") or "").strip()
        quantity = str(line.get("quantity_per_serving_g") or "").strip()
        matched = _ingredient_by_exact_name(session, ingredient_name) if ingredient_name else None
        if matched is None:
            warnings.append(f"食材库里没有「{ingredient_name}」，先建这条食材再录配方")
        resolved.append(
            {
                "食材": ingredient_name,
                "单份用量_克": quantity,
                "库里匹配": None if matched is None else matched.name,
            }
        )
        if matched is not None and quantity:
            payload_items.append(
                {"ingredient_id": str(matched.id), "quantity_per_serving_g": quantity}
            )

    resolved_seasonings: list[dict[str, Any]] = []
    payload_seasonings: list[dict[str, Any]] = []
    for line in seasoning_items or []:
        seasoning_name = str(line.get("seasoning_name") or "").strip()
        quantity = str(line.get("quantity_per_serving_g") or "").strip()
        matched_seasoning = (
            _seasoning_by_exact_name(session, seasoning_name) if seasoning_name else None
        )
        if matched_seasoning is None:
            warnings.append(f"调味料库里没有「{seasoning_name}」")
        resolved_seasonings.append(
            {
                "调味料": seasoning_name,
                "单份用量_克": quantity,
                "库里匹配": None if matched_seasoning is None else matched_seasoning.name,
            }
        )
        if matched_seasoning is not None and quantity:
            payload_seasonings.append(
                {"seasoning_id": str(matched_seasoning.id), "quantity_per_serving_g": quantity}
            )

    if not payload_items:
        warnings.append("配方里至少要有一行能对上库里食材的用量，否则算不出营养")
    blocking = [item for item in warnings if "没有" in item or "至少要有一行" in item]
    summary = (
        f"新增菜品「{name}」（{category}/{cooking_method}），配方 {len(payload_items)} 行食材、"
        f"{len(payload_seasonings)} 行调味料"
    )
    if blocking:
        summary += "；先解决：" + "；".join(blocking)
    return {
        "title": f"新增菜品：{name}",
        "summary": summary,
        "preview": {
            "将新增": {
                "菜品": name,
                "类别": category,
                "做法": cooking_method,
                "标准份量_克": standard_serving_g,
                "单锅制作份数": servings_per_pot,
                "过敏原": allergens or [],
            },
            "配方食材": resolved,
            "配方调味料": resolved_seasonings,
            "提示": [
                *warnings,
                "保存后系统会按配方自动算出单份营养（含可食部折算与调味料分摊）",
            ],
            "动作": "新增菜品并录入配方",
        },
        "payload": {
            "name": name,
            "category": category,
            "cooking_method": cooking_method,
            "standard_serving_g": standard_serving_g,
            "servings_per_pot": servings_per_pot,
            "allergens": allergens or [],
            "recipe": {"ingredients": payload_items, "seasonings": payload_seasonings},
        },
    }


def create_dish_execute(session: Session, payload: dict[str, Any], *, actor: Any) -> dict[str, Any]:
    from app.modules.dish.schemas import DishCreate, RecipePayload

    created = dish_service.create_dish(
        session,
        DishCreate(
            name=payload["name"],
            category=payload["category"],
            cooking_method=payload["cooking_method"],
            standard_serving_g=payload["standard_serving_g"],
            servings_per_pot=payload.get("servings_per_pot") or payload["standard_serving_g"],
            allergens=payload.get("allergens") or [],
            recipe=RecipePayload(
                ingredients=payload["recipe"]["ingredients"],
                seasonings=payload["recipe"].get("seasonings") or [],
            ),
        ),
        actor_id=actor.id,
        actor_name=actor.display_name,
        audit_note="经「AI 助手」提议、由本人确认后创建",
    )
    return {
        "实体": "菜品",
        "id": str(created.id),
        "菜品": created.name,
        "单份能量_千卡": None if created.nutrition is None else created.nutrition.energy_kcal,
    }


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


# ---------------------------------------------------------------------------
# 注册表
# ---------------------------------------------------------------------------
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
    Tool(
        name="create_ingredient",
        label="新增食材",
        description=(
            "在食材库新增一条食材。**这是写操作：调用它不会立刻写库，而是生成一份待确认的方案**，"
            "要让用户确认后才真正执行。数据来源（data_source）必填——营养数据必须可追溯。"
        ),
        parameters=_schema(
            {
                "name": {"type": "string", "description": "食材名称，例如「西兰花」"},
                "category": {
                    "type": "string",
                    "description": "食材类别代码：GRAIN/VEGETABLE/FRUIT/LIVESTOCK_POULTRY/AQUATIC/"
                    "EGG/DAIRY/BEAN/NUT/FUNGUS_ALGAE/OIL_FAT/CONDIMENT",
                },
                "data_source": {
                    "type": "string",
                    "description": "数据来源，必填，例如《中国食物成分表（标准版第 6 版）》",
                },
                "energy_kcal": {"type": "string", "description": "能量（千卡/100 克可食部）"},
                "protein_g": {"type": "string", "description": "蛋白质（克/100 克可食部）"},
                "fat_g": {"type": "string", "description": "脂肪（克/100 克可食部）"},
                "carb_g": {"type": "string", "description": "碳水（克/100 克可食部）"},
                "sodium_mg": {"type": "string", "description": "钠（毫克/100 克可食部）"},
                "edible_ratio": {"type": "string", "description": "可食部比例 0~1，默认 1"},
                "unit_price": {"type": "string", "description": "单价（元/公斤市品）"},
                "source_version": {"type": "string", "description": "来源版本"},
                "note": {"type": "string", "description": "备注"},
            },
            required=["name", "category", "data_source"],
        ),
        handler=create_ingredient_draft,
        read_only=False,
        build_draft=create_ingredient_draft,
        execute=create_ingredient_execute,
    ),
    Tool(
        name="create_dish_with_recipe",
        label="新增菜品与配方",
        description=(
            "新增一道菜并一次录入它的配方（单份食材用量与调味料分摊）。"
            "**这是写操作：调用它不会立刻写库，而是生成一份待确认的方案**，要让用户确认后才执行。"
            "配方里的食材必须已经在食材库里；对不上的会在方案里点出来，先建食材再录配方。"
        ),
        parameters=_schema(
            {
                "name": {"type": "string", "description": "菜品名称"},
                "category": {
                    "type": "string",
                    "description": "菜品类别代码：STAPLE/SOUP/MEAT/HALF_MEAT/VEGETABLE/OTHER",
                },
                "cooking_method": {
                    "type": "string",
                    "description": "烹饪方式代码：STEAM/BOIL/STIR_FRY/DEEP_FRY/BRAISE/COLD_MIX",
                },
                "standard_serving_g": {"type": "string", "description": "标准份量（克）"},
                "servings_per_pot": {"type": "string", "description": "单锅制作份数"},
                "allergens": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "过敏原",
                },
                "recipe_items": {
                    "type": "array",
                    "description": "配方食材，每行一份单份用量（克，市品重量）",
                    "items": {
                        "type": "object",
                        "properties": {
                            "ingredient_name": {"type": "string"},
                            "quantity_per_serving_g": {"type": "string"},
                        },
                        "required": ["ingredient_name", "quantity_per_serving_g"],
                    },
                },
                "seasoning_items": {
                    "type": "array",
                    "description": "配方里分摊到单份的调味料用量（克）",
                    "items": {
                        "type": "object",
                        "properties": {
                            "seasoning_name": {"type": "string"},
                            "quantity_per_serving_g": {"type": "string"},
                        },
                        "required": ["seasoning_name", "quantity_per_serving_g"],
                    },
                },
            },
            required=["name", "category", "cooking_method", "standard_serving_g", "recipe_items"],
        ),
        handler=create_dish_draft,
        read_only=False,
        build_draft=create_dish_draft,
        execute=create_dish_execute,
    ),
)

TOOLS_BY_NAME: dict[str, Tool] = {tool.name: tool for tool in TOOLS}

#: 阶段一允许使用的角色。读操作对三个角色都开放：学校管理方本来就是只读观察者。
ALLOWED_ROLES: frozenset[UserRole] = frozenset(
    {UserRole.RECORDER, UserRole.CANTEEN_ADMIN, UserRole.SCHOOL_ADMIN}
)


def assert_write_boundary() -> None:
    """自查：没有哪个工具能绕过「人工确认」直接写库。

    两类工具各有各的规矩：

    - 读工具不许带执行入口——带了就意味着它可能在一次对话里就把东西改了；
    - 写工具必须同时有「出方案」与「执行」两步——只有执行没有方案，等于没有确认这一环。

    这条不靠提示词自律，靠结构：`execute` 只在确认路径上被调用（见 service.confirm_proposal）。
    写成一个函数并由测试调用，是为了以后有人加工具时当场被拦住。
    """
    for tool in TOOLS:
        if tool.read_only:
            if tool.execute is not None or tool.build_draft is not None:
                raise AssertionError(f"读工具 {tool.name} 不该带写操作入口")
            continue
        if tool.build_draft is None or tool.execute is None:
            raise AssertionError(
                f"写工具 {tool.name} 必须同时提供方案与执行两步，否则可以绕过人工确认"
            )


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

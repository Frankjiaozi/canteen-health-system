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
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import BusinessRuleError
from app.modules.analytics import service as analytics_service
from app.modules.collection import service as collection_service
from app.modules.dish import service as dish_service
from app.modules.ingredient import service as ingredient_service
from app.modules.seasoning import service as seasoning_service
from app.shared.enums import DishCategory, IngredientCategory, MealType, UserRole

#: 一次最多回几条：助手是给人看结论的，不是导数据用的。要全量请去对应页面。
MAX_ROWS = 20


def today() -> date:
    return datetime.now(get_settings().timezone).date()


def _num(value: Decimal | None) -> str | None:
    """小数按人看得懂的方式给：去掉无意义的尾零，且**不要科学计数法**。

    `Decimal("150.000").normalize()` 会得到 `1.5E+2`——那是给机器看的，
    模型和用户看到「标准份量 1.5E+2 克」只会一头雾水。`format(..., "f")` 强制普通写法。
    """
    if value is None:
        return None
    return format(value.normalize(), "f")


def _raw(value: Any) -> Any:
    """撤回快照要能存进 JSONB，所以 Decimal 之类的统一转成字符串。"""
    if isinstance(value, Decimal):
        return str(value)
    return value


def _display(value: Any) -> str | None:
    """把字段值变成给人看的样子。

    字段里既有 Decimal（营养值、单价），也有枚举（类别、做法）和纯文本（来源、备注），
    所以不能一律当成小数处理——早期版本对文本调 `normalize()` 会直接崩。
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return _num(value)
    label = getattr(value, "label", None)
    return str(label) if label is not None else str(value)


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
    #: 读工具的实现：调用即查询。写工具没有它——写工具只能出方案（`build_draft`）然后执行
    handler: Callable[..., dict[str, Any]] | None = None
    read_only: bool = True
    #: 写工具专用：把参数整理成一份给人看的方案 + 将要执行的参数
    build_draft: Callable[..., dict[str, Any]] | None = None
    #: 写工具专用：用户确认之后才执行
    execute: Callable[..., ExecutionOutcome] | None = None
    #: 只给「撤回」用、不给模型看的工具（例如重新启用、退回上一条采集）
    hidden: bool = False


@dataclass(frozen=True, slots=True)
class UndoStep:
    """撤回时要执行的一步。存成数据而不是闭包，才能落库、跨进程重放。"""

    tool: str
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ExecutionOutcome:
    """一次确认执行的结果，外加「怎么撤回」。

    `undo` 由 execute 在执行**当时**给出：撤回要把数据改回执行之前的样子，
    而那套值只有在那一刻是准确的（事后再去推，推出来的不敢往下写）。
    """

    result: dict[str, Any]
    undo: tuple[UndoStep, ...] = ()


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
) -> ExecutionOutcome:
    """确认之后真正写库。走的是食材域自己的 service，审计与校验与页面录入完全一致。"""
    from app.modules.ingredient.schemas import IngredientCreate

    created = ingredient_service.create_ingredient(
        session,
        IngredientCreate(**payload),
        actor_id=actor.id,
        actor_name=actor.display_name,
        audit_note="经「AI 助手」提议、由本人确认后创建",
    )
    return ExecutionOutcome(
        result={"实体": "食材", "id": str(created.id), "名称": created.name},
        # 撤回「新增」= 停用它（软删除）。不物理删除：被配方引用过的数据要留得住
        undo=(
            UndoStep(
                tool="deactivate_ingredient",
                payload={"ingredient_id": str(created.id), "reason": "撤回助手新建的食材"},
            ),
        ),
    )


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


def create_dish_execute(
    session: Session, payload: dict[str, Any], *, actor: Any
) -> ExecutionOutcome:
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
    return ExecutionOutcome(
        result={
            "实体": "菜品",
            "id": str(created.id),
            "菜品": created.name,
            "单份能量_千卡": None if created.nutrition is None else created.nutrition.energy_kcal,
        },
        undo=(
            UndoStep(
                tool="deactivate_dish",
                payload={"dish_id": str(created.id), "reason": "撤回助手新建的菜品"},
            ),
        ),
    )


#: 菜品可改的基础字段（配方是另一条路：整体替换）
DISH_EDITABLE = {
    "category": "类别",
    "cooking_method": "做法",
    "standard_serving_g": "标准份量_克",
    "servings_per_pot": "单锅制作份数",
    "note": "备注",
}


def update_dish_draft(
    session: Session,
    *,
    name: str,
    category: str | None = None,
    cooking_method: str | None = None,
    standard_serving_g: str | None = None,
    servings_per_pot: str | None = None,
    note: str | None = None,
    recipe_items: list[dict[str, Any]] | None = None,
    seasoning_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """修改菜品：基础信息按字段改，配方是**整体替换**（与页面上同一个语义）。"""
    dish = _dish_or_fail(session, name)
    changes = {
        field: value
        for field, value in (
            ("category", category),
            ("cooking_method", cooking_method),
            ("standard_serving_g", standard_serving_g),
            ("servings_per_pot", servings_per_pot),
            ("note", note),
        )
        if value not in (None, "")
    }
    warnings: list[str] = []
    recipe_payload: dict[str, Any] | None = None
    resolved: list[dict[str, Any]] = []
    if recipe_items:
        payload_items: list[dict[str, Any]] = []
        for line in recipe_items:
            ingredient_name = str(line.get("ingredient_name") or "").strip()
            quantity = str(line.get("quantity_per_serving_g") or "").strip()
            matched = (
                _ingredient_by_exact_name(session, ingredient_name) if ingredient_name else None
            )
            if matched is None:
                warnings.append(f"食材库里没有「{ingredient_name}」，先建这条食材再改配方")
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
        payload_seasonings: list[dict[str, Any]] = []
        for line in seasoning_items or []:
            seasoning_name = str(line.get("seasoning_name") or "").strip()
            matched_seasoning = (
                _seasoning_by_exact_name(session, seasoning_name) if seasoning_name else None
            )
            if matched_seasoning is None:
                warnings.append(f"调味料库里没有「{seasoning_name}」")
                continue
            payload_seasonings.append(
                {
                    "seasoning_id": str(matched_seasoning.id),
                    "quantity_per_serving_g": line.get("quantity_per_serving_g"),
                }
            )
        recipe_payload = {"ingredients": payload_items, "seasonings": payload_seasonings}
        warnings.append(
            f"配方是**整体替换**：原来的配方会被这一份（{len(resolved)} 行食材）换掉，版本号 +1，"
            "并重算历史上所有用过它的日子的营养结果"
        )
    if not changes and recipe_payload is None:
        warnings.append("没有给出任何要改的内容")

    detail = dish_service.get_dish_detail(session, dish.id)
    return {
        "title": f"修改菜品：{dish.name}",
        "summary": (
            f"改菜品「{dish.name}」的 " + "、".join(DISH_EDITABLE[field] for field in changes)
            if changes and recipe_payload is None
            else (
                f"替换菜品「{dish.name}」的配方"
                if recipe_payload is not None and not changes
                else f"改菜品「{dish.name}」的基础信息并替换配方"
            )
        ),
        "preview": {
            "将修改": [
                {
                    "字段": DISH_EDITABLE[field],
                    "现在": _display(getattr(dish, field)),
                    "改成": value,
                }
                for field, value in changes.items()
            ],
            "新配方食材": resolved or None,
            "当前配方": None
            if detail.recipe is None
            else [
                {"食材": item.ingredient_name, "单份用量_克": item.quantity_per_serving_g}
                for item in detail.recipe.ingredients
            ],
            "提示": [*warnings, "确认后可以在这条方案上「撤回」，改回原来的字段与配方"],
        },
        "payload": {
            "dish_id": str(dish.id),
            "changes": changes,
            "recipe": recipe_payload,
        },
    }


def update_dish_execute(
    session: Session, payload: dict[str, Any], *, actor: Any
) -> ExecutionOutcome:
    from app.modules.dish.schemas import DishUpdate, RecipePayload

    dish_id = UUID(str(payload["dish_id"]))
    changes: dict[str, Any] = dict(payload.get("changes") or {})
    recipe_payload: dict[str, Any] | None = payload.get("recipe")
    detail_before = dish_service.get_dish_detail(session, dish_id)
    before_fields = {field: _raw(getattr(detail_before, field)) for field in changes}
    before_recipe = (
        None
        if detail_before.recipe is None
        else {
            "ingredients": [
                {
                    "ingredient_id": str(item.ingredient_id),
                    "quantity_per_serving_g": str(item.quantity_per_serving_g),
                }
                for item in detail_before.recipe.ingredients
            ],
            "seasonings": [
                {
                    "seasoning_id": str(item.seasoning_id),
                    "quantity_per_serving_g": str(item.quantity_per_serving_g),
                }
                for item in detail_before.recipe.seasonings
            ],
        }
    )

    note = "经「AI 助手」提议、由本人确认后修改"
    if changes:
        dish_service.update_dish(
            session,
            dish_id,
            DishUpdate(**changes),
            actor_id=actor.id,
            actor_name=actor.display_name,
            audit_note=note,
        )
    recomputed = 0
    if recipe_payload:
        result = dish_service.replace_recipe(
            session,
            dish_id,
            RecipePayload(
                ingredients=recipe_payload["ingredients"],
                seasonings=recipe_payload.get("seasonings") or [],
            ),
            actor_id=actor.id,
            actor_name=actor.display_name,
            audit_note=note,
        )
        recomputed = result.recomputed_rows

    after = dish_service.get_dish_detail(session, dish_id)
    undo_steps: list[UndoStep] = []
    if before_recipe is not None or recipe_payload is not None:
        undo_steps.append(
            UndoStep(
                tool="update_dish",
                payload={
                    "dish_id": str(dish_id),
                    "changes": before_fields,
                    "recipe": before_recipe,
                },
            )
        )
    elif before_fields:
        undo_steps.append(
            UndoStep(
                tool="update_dish",
                payload={"dish_id": str(dish_id), "changes": before_fields},
            )
        )
    return ExecutionOutcome(
        result={
            "实体": "菜品",
            "id": str(dish_id),
            "菜品": after.name,
            "改了": list(changes) + (["配方"] if recipe_payload else []),
            "重算营养结果": recomputed,
        },
        undo=tuple(undo_steps),
    )


def deactivate_dish_draft(
    session: Session, *, name: str, reason: str | None = None
) -> dict[str, Any]:
    """停用菜品（软删除）。预览里说明它被历史菜单引用过多少次。"""
    dish = _dish_or_fail(session, name)
    used = dish_service.dish_menu_usage(session, dish.id)
    warnings = [
        f"有 {used} 天供应过它；停用之后它不再出现在菜单与推荐里，历史数据与营养结果都保留（可以再启用）"
    ]
    if reason:
        warnings.append(f"理由：{reason}")
    return {
        "title": f"停用菜品：{dish.name}",
        "summary": f"把菜品「{dish.name}」停用（软删除，历史菜单引用 {used} 次）",
        "preview": {
            "将停用": {"菜品": dish.name, "类别": dish.category_label, "被引用": used},
            "提示": [*warnings, "可以撤回"],
        },
        "payload": {"dish_id": str(dish.id), "reason": reason},
    }


def deactivate_dish_execute(
    session: Session, payload: dict[str, Any], *, actor: Any
) -> ExecutionOutcome:
    dish_id = UUID(str(payload["dish_id"]))
    reason = payload.get("reason") or None
    note = "经「AI 助手」提议、由本人确认后停用"
    if reason:
        note = f"{note}（{reason}）"
    stopped = dish_service.deactivate_dish(
        session,
        dish_id,
        actor_id=actor.id,
        actor_name=actor.display_name,
        audit_note=note,
    )
    return ExecutionOutcome(
        result={"实体": "菜品", "id": str(dish_id), "菜品": stopped.name, "状态": "已停用"},
        undo=(UndoStep(tool="reactivate_dish", payload={"dish_id": str(dish_id)}),),
    )


def reactivate_ingredient_execute(
    session: Session, payload: dict[str, Any], *, actor: Any
) -> ExecutionOutcome:
    """撤回「停用食材」时要走的那一步。只给撤回用，不暴露给模型。"""
    ingredient_id = UUID(str(payload["ingredient_id"]))
    restored = ingredient_service.reactivate_ingredient(
        session,
        ingredient_id,
        actor_id=actor.id,
        actor_name=actor.display_name,
        audit_note="撤回 AI 助手的停用：重新启用",
    )
    return ExecutionOutcome(
        result={"实体": "食材", "id": str(restored.id), "名称": restored.name, "状态": "已启用"}
    )


def reactivate_dish_execute(
    session: Session, payload: dict[str, Any], *, actor: Any
) -> ExecutionOutcome:
    """撤回「停用菜品」时要走的那一步。只给撤回用。"""
    dish_id = UUID(str(payload["dish_id"]))
    restored = dish_service.reactivate_dish(
        session,
        dish_id,
        actor_id=actor.id,
        actor_name=actor.display_name,
        audit_note="撤回 AI 助手的停用：重新启用",
    )
    return ExecutionOutcome(
        result={"实体": "菜品", "id": str(dish_id), "菜品": restored.name, "状态": "已启用"}
    )


# 改与停用：同样是「先出方案、确认后执行」，但要多给两样东西
# ---------------------------------------------------------------------------
#: 改与停用的预览都要带上「影响面」与「怎么撤回」——这两样缺了，用户就是在盲签
INGREDIENT_EDITABLE = {
    "energy_kcal": "能量_千卡每100克",
    "protein_g": "蛋白质_克每100克",
    "fat_g": "脂肪_克每100克",
    "carb_g": "碳水_克每100克",
    "sodium_mg": "钠_毫克每100克",
    "edible_ratio": "可食部比例",
    "unit_price": "单价_元每公斤市品",
    "data_source": "数据来源",
    "source_version": "来源版本",
    "note": "备注",
}


def _ingredient_or_fail(session: Session, name: str) -> Any:
    ingredient = _ingredient_by_exact_name(session, name)
    if ingredient is None:
        raise BusinessRuleError(f"食材库里没有「{name}」，先确认名字（可以先查一下食材库）")
    return ingredient


def _dish_or_fail(session: Session, name: str) -> Any:
    page = dish_service.list_dishes(session, keyword=name, page=1, page_size=MAX_ROWS)
    dish = next((row for row in page.items if row.name == name), None)
    if dish is None:
        raise BusinessRuleError(f"菜品库里没有「{name}」，先确认名字（可以先查一下菜品）")
    return dish


def update_ingredient_draft(
    session: Session,
    *,
    name: str,
    energy_kcal: str | None = None,
    protein_g: str | None = None,
    fat_g: str | None = None,
    carb_g: str | None = None,
    sodium_mg: str | None = None,
    edible_ratio: str | None = None,
    unit_price: str | None = None,
    data_source: str | None = None,
    source_version: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """修改食材。预览里把「现在的值 → 改成什么」逐项列出来。"""
    ingredient = _ingredient_or_fail(session, name)
    changes = {
        field: value
        for field, value in (
            ("energy_kcal", energy_kcal),
            ("protein_g", protein_g),
            ("fat_g", fat_g),
            ("carb_g", carb_g),
            ("sodium_mg", sodium_mg),
            ("edible_ratio", edible_ratio),
            ("unit_price", unit_price),
            ("data_source", data_source),
            ("source_version", source_version),
            ("note", note),
        )
        if value not in (None, "")
    }
    current = {
        "名称": ingredient.name,
        **{
            label: _display(getattr(ingredient, field))
            for field, label in INGREDIENT_EDITABLE.items()
        },
    }
    warnings: list[str] = []
    if not changes:
        warnings.append("没有给出任何要修改的字段，请说明改哪一项、改成多少")
    if "energy_kcal" in changes or "data_source" in changes:
        warnings.append(
            "改了营养成分或来源之后，用到这个食材的菜品营养结果需要重算才准"
            "（保存时系统会按配方重算历史结果）"
        )
    return {
        "title": f"修改食材：{ingredient.name}",
        "summary": f"把食材「{ingredient.name}」的 "
        + "、".join(INGREDIENT_EDITABLE[field] for field in changes)
        + " 改掉",
        "preview": {
            "将修改": [
                {
                    "字段": INGREDIENT_EDITABLE[field],
                    "现在": current.get(INGREDIENT_EDITABLE[field], "—"),
                    "改成": value,
                }
                for field, value in changes.items()
            ],
            "当前值": current,
            "提示": [*warnings, "确认后可以在这条方案上「撤回」，改回原来的值"],
        },
        "payload": {"ingredient_id": str(ingredient.id), "changes": changes},
    }


def update_ingredient_execute(
    session: Session, payload: dict[str, Any], *, actor: Any
) -> ExecutionOutcome:
    from app.modules.ingredient.schemas import IngredientUpdate

    ingredient_id = UUID(str(payload["ingredient_id"]))
    changes: dict[str, Any] = dict(payload["changes"])
    # 撤回要把这些字段改回原样，所以先记下它们「原来是什么」。
    # 这份快照只在执行这一刻是准的，因此由 execute 给出、随方案一起落库
    current = ingredient_service.get_ingredient(session, ingredient_id)
    before = {field: _raw(getattr(current, field)) for field in changes}

    updated = ingredient_service.update_ingredient(
        session,
        ingredient_id,
        IngredientUpdate(**changes),
        actor_id=actor.id,
        actor_name=actor.display_name,
        audit_note="经「AI 助手」提议、由本人确认后修改",
    )
    return ExecutionOutcome(
        result={"实体": "食材", "id": str(updated.id), "名称": updated.name, "改了": list(changes)},
        undo=(
            UndoStep(
                tool="update_ingredient",
                payload={"ingredient_id": str(ingredient_id), "changes": before},
            ),
        ),
    )


def deactivate_ingredient_draft(
    session: Session, *, name: str, reason: str | None = None
) -> dict[str, Any]:
    """停用食材（软删除）。预览里说明它被多少配方用着——这就是影响面。"""
    ingredient = _ingredient_or_fail(session, name)
    used = dish_service.count_recipes_using_ingredient(session, ingredient.id)
    warnings = [
        f"有 {used} 个配方在用它；停用之后这些菜品的营养计算会缺这一项（数据不删除，可以再启用）"
    ]
    if reason:
        warnings.append(f"理由：{reason}")
    return {
        "title": f"停用食材：{ingredient.name}",
        "summary": f"把食材「{ingredient.name}」停用（软删除，{used} 个配方引用中）",
        "preview": {
            "将停用": {"名称": ingredient.name, "类别": ingredient.category_label, "被引用": used},
            "提示": [
                *warnings,
                "停用只是从可选清单里拿掉，历史记录与营养结果都保留；可以撤回",
            ],
        },
        "payload": {"ingredient_id": str(ingredient.id), "reason": reason},
    }


def deactivate_ingredient_execute(
    session: Session, payload: dict[str, Any], *, actor: Any
) -> ExecutionOutcome:
    ingredient_id = UUID(str(payload["ingredient_id"]))
    reason = payload.get("reason") or None
    note = "经「AI 助手」提议、由本人确认后停用"
    if reason:
        note = f"{note}（{reason}）"
    stopped = ingredient_service.deactivate_ingredient(
        session,
        ingredient_id,
        actor_id=actor.id,
        actor_name=actor.display_name,
        audit_note=note,
    )
    return ExecutionOutcome(
        result={"实体": "食材", "id": str(stopped.id), "名称": stopped.name, "状态": "已停用"},
        undo=(
            UndoStep(
                tool="reactivate_ingredient",
                payload={"ingredient_id": str(ingredient_id)},
            ),
        ),
    )


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
        read_only=False,
        build_draft=create_dish_draft,
        execute=create_dish_execute,
    ),
    Tool(
        name="update_ingredient",
        label="修改食材",
        description=(
            "修改食材库里的营养值、可食部、单价、来源或备注。"
            "**写操作：调用只生成待确认的方案**（含「现在的值 → 改成什么」），要用户确认后才执行。"
            "用 name 定位食材（库里叫什么就写什么），其余字段只给要改的。"
        ),
        parameters=_schema(
            {
                "name": {"type": "string", "description": "要改的食材名称（库里现有名字）"},
                "energy_kcal": {"type": "string", "description": "能量（千卡/100 克可食部）"},
                "protein_g": {"type": "string"},
                "fat_g": {"type": "string"},
                "carb_g": {"type": "string"},
                "sodium_mg": {"type": "string"},
                "edible_ratio": {"type": "string", "description": "可食部比例 0~1"},
                "unit_price": {"type": "string", "description": "单价（元/公斤市品）"},
                "data_source": {"type": "string", "description": "数据来源（改了要能追溯）"},
                "source_version": {"type": "string"},
                "note": {"type": "string"},
            },
            required=["name"],
        ),
        read_only=False,
        build_draft=update_ingredient_draft,
        execute=update_ingredient_execute,
    ),
    Tool(
        name="deactivate_ingredient",
        label="停用食材",
        description=(
            "把食材停用（软删除：从可选清单里拿掉，历史数据保留、可以再启用）。"
            "**写操作：调用只生成待确认的方案**，方案里会写明有多少个配方在用它。"
        ),
        parameters=_schema(
            {
                "name": {"type": "string", "description": "食材名称"},
                "reason": {"type": "string", "description": "停用理由（会记进留痕）"},
            },
            required=["name"],
        ),
        read_only=False,
        build_draft=deactivate_ingredient_draft,
        execute=deactivate_ingredient_execute,
    ),
    Tool(
        name="update_dish",
        label="修改菜品与配方",
        description=(
            "改菜品的类别、做法、标准份量等；也可以**整体替换配方**（给 recipe_items 时）。"
            "**写操作：调用只生成待确认的方案**。配方是整体替换语义，方案里会列出原配方与新配方。"
        ),
        parameters=_schema(
            {
                "name": {"type": "string", "description": "菜品名称（库里现有名字）"},
                "category": {
                    "type": "string",
                    "description": "类别代码：STAPLE/SOUP/MEAT/HALF_MEAT/VEGETABLE/OTHER",
                },
                "cooking_method": {
                    "type": "string",
                    "description": "做法代码：STEAM/BOIL/STIR_FRY/DEEP_FRY/BRAISE/COLD_MIX",
                },
                "standard_serving_g": {"type": "string"},
                "servings_per_pot": {"type": "string"},
                "note": {"type": "string"},
                "recipe_items": {
                    "type": "array",
                    "description": "给了就整体替换配方；每行一份单份用量（克，市品重量）",
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
            required=["name"],
        ),
        read_only=False,
        build_draft=update_dish_draft,
        execute=update_dish_execute,
    ),
    Tool(
        name="deactivate_dish",
        label="停用菜品",
        description=(
            "把菜品停用（软删除：不再出现在菜单与推荐里，历史营养结果保留、可以再启用）。"
            "**写操作：调用只生成待确认的方案**，方案里会写明被历史菜单引用过多少次。"
        ),
        parameters=_schema(
            {
                "name": {"type": "string", "description": "菜品名称"},
                "reason": {"type": "string", "description": "停用理由（会记进留痕）"},
            },
            required=["name"],
        ),
        read_only=False,
        build_draft=deactivate_dish_draft,
        execute=deactivate_dish_execute,
    ),
    Tool(
        name="reactivate_ingredient",
        label="重新启用食材",
        description="撤回「停用食材」时用。不直接暴露给模型调用。",
        parameters=_schema({"ingredient_id": {"type": "string"}}, required=["ingredient_id"]),
        read_only=False,
        build_draft=lambda session, **kwargs: kwargs,
        execute=reactivate_ingredient_execute,
        hidden=True,
    ),
    Tool(
        name="reactivate_dish",
        label="重新启用菜品",
        description="撤回「停用菜品」时用。不直接暴露给模型调用。",
        parameters=_schema({"dish_id": {"type": "string"}}, required=["dish_id"]),
        read_only=False,
        build_draft=lambda session, **kwargs: kwargs,
        execute=reactivate_dish_execute,
        hidden=True,
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
            if tool.handler is None:
                raise AssertionError(f"读工具 {tool.name} 没有实现")
            if tool.execute is not None or tool.build_draft is not None:
                raise AssertionError(f"读工具 {tool.name} 不该带写操作入口")
            continue
        if tool.build_draft is None or tool.execute is None:
            raise AssertionError(
                f"写工具 {tool.name} 必须同时提供方案与执行两步，否则可以绕过人工确认"
            )
        if tool.handler is not None:
            raise AssertionError(f"写工具 {tool.name} 不该有直接执行入口 handler")


def tool_payload() -> list[dict[str, Any]]:
    """给模型看的工具清单（OpenAI 的函数调用格式）。

    隐藏工具不在这里出现：它们只服务于「撤回」，模型自己调没有意义——
    那会让「撤回」变成模型的一次自由发挥，而不是用户点按钮的结果。
    """
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
        if not tool.hidden
    ]


# ---------------------------------------------------------------------------

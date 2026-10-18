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

import json
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
from app.modules.menu import service as menu_service
from app.modules.menu.locking import lock_meal
from app.modules.menuplan import publication
from app.modules.menuplan import service as menuplan_service
from app.modules.nutrition import service as nutrition_service
from app.modules.recommendation import service as recommendation_service
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
    # 布尔要写成「是 / 否」：「现在 True → 改成 False」在确认卡片上没法看，
    # 而这正是用户要核对的最后一眼
    if isinstance(value, bool):
        return "是" if value else "否"
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


def _spec_parameters(path: str) -> tuple[list[str], list[str]]:
    """这个 GET 接口的必填与可选查询参数。从 OpenAPI 里读，不手写。"""
    from app.main import app as application

    get = ((application.openapi().get("paths") or {}).get(path) or {}).get("get") or {}
    required: list[str] = []
    optional: list[str] = []
    for parameter in get.get("parameters") or []:
        name = str(parameter.get("name") or "")
        if not name:
            continue
        (required if parameter.get("required") else optional).append(name)
    return required, optional


def list_read_apis(session: Session, *, prefix: str | None = None) -> dict[str, Any]:
    """列出助手能调的只读接口**以及每个接口需要的参数**。

    为什么要有这个工具：模型不知道某个接口要哪些参数，只能先试一次、吃个 422、再改一次——
    每试一次花掉一轮工具调用。实测它就是在这一步把轮次预算烧光的。把参数一次给全，
    它就能一次调对。
    """
    paths = read_api_paths()
    if prefix:
        paths = tuple(path for path in paths if prefix in path)
    rows = []
    for path in paths:
        required, optional = _spec_parameters(path)
        rows.append({"路径": path, "必填参数": required, "可选参数": optional})
    return {
        "接口": rows,
        "说明": "只读接口的清单与参数。写操作不在其中——那些要用专门的工具（会先出方案、要人确认）",
    }


# ---------------------------------------------------------------------------
# 通用只读出口：call_api
# ---------------------------------------------------------------------------
#: 白名单缓存：从路由表里取出来的 GET 路径
_READ_PATHS: tuple[str, ...] | None = None

#: 一次最多回多少字符。超了就截断并说明——对话里塞一整页 JSON 对模型和人都没用。
MAX_API_CHARS = 6000


def read_api_paths() -> tuple[str, ...]:
    """助手允许调的 GET 路径。**从 OpenAPI 文档生成**，不是手写清单——接口加了就自动进来，不会过期。

    只收「列举式」的 GET（路径里没有 `{...}` 占位符）：

    - 带占位符的是单条查询（`/ingredients/{id}`），模型手里通常没有那些 id，
      而且这类数据现有工具已经覆盖了；
    - 非 JSON 的响应（例如 Excel 模板）也排除——那不是给对话用的；
    - 助手自己的接口排除掉，不给自己套娃。

    为什么用 OpenAPI 而不是遍历 `api_router.routes`：新版 FastAPI 把子路由**嵌套**保存，
    直接遍历拿到的是 14 个空壳（没有 path 与 methods），得自己递归——而 OpenAPI 文档本来就是扁平的，
    还顺带给出每个响应的内容类型，正好用来排除非 JSON 的接口。
    """
    global _READ_PATHS
    if _READ_PATHS is None:
        # 延迟导入：模块级导入会成环（api → assistant.router → service → tools）
        from app.main import app as application

        prefixes = (
            "/api/v1/meta",
            "/api/v1/ingredients",
            "/api/v1/seasonings",
            "/api/v1/dishes",
            "/api/v1/collection",
            # 注意这里用的是**接口前缀**而不是模块名：看板挂在 /dashboard、三层校准挂在 /calibration
            "/api/v1/dashboard",
            "/api/v1/calibration",
            "/api/v1/forecast",
            "/api/v1/recommendation",
            "/api/v1/public",
        )
        paths: set[str] = set()
        for path, operations in (application.openapi().get("paths") or {}).items():
            get = (operations or {}).get("get")
            if get is None or "{" in path:
                continue
            if not path.startswith(prefixes):
                continue
            content = ((get.get("responses") or {}).get("200") or {}).get("content") or {}
            if "application/json" not in content:
                continue  # 例如 Excel 模板：不是给对话用的
            paths.add(path)
        _READ_PATHS = tuple(sorted(paths))
    return _READ_PATHS


def call_api(
    session: Session,
    *,
    actor: Any,
    path: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """调一个**只读**接口，把结果拿回来。给「现有工具没覆盖、但接口里有」的查询兜底。

    三条设计：

    1. **只读**：白名单里全是 GET，写操作一个也不放行——写必须走「出方案 → 人确认」那条路。
    2. **以当前用户的身份调**：用他的身份签一个短期令牌发给自己，**完整走一遍依赖链**，
       所以角色校验、参数校验、序列化都跟界面上一样，不存在「助手有特权」。
    3. **走进程内的应用**（TestClient），不依赖网络与端口。
    """
    allowed = read_api_paths()
    if path not in allowed:
        raise BusinessRuleError(
            f"这个路径不能调：{path}。只允许只读查询，可用的有：" + "、".join(allowed)
        )

    # 延迟导入：同上，避免模块级成环
    from fastapi.testclient import TestClient

    from app.core.config import get_settings
    from app.core.security import create_access_token
    from app.main import app as application

    settings = get_settings()
    token = create_access_token(user_id=actor.id, username=actor.username, role=actor.role)
    client = TestClient(application)
    client.cookies.set(settings.cookie_name, token)
    try:
        response = client.get(path, params=params or {})
    finally:
        client.close()

    if response.status_code >= 400:
        required, optional = _spec_parameters(path)
        hint = (
            f"这个接口需要：必填 {'、'.join(required) or '无'}"
            f"；可选 {'、'.join(optional) or '无'}。补齐之后再试一次。"
        )
        raise BusinessRuleError(f"接口返回 {response.status_code}：{response.text[:200]}。{hint}")
    try:
        payload = response.json()
    except ValueError as error:
        raise BusinessRuleError("这个接口返回的不是 JSON，没法在对话里用") from error

    text = json.dumps(payload, ensure_ascii=False, default=str)
    truncated = len(text) > MAX_API_CHARS
    # 分页接口返回的是 {items: [], total: 0}，不是空列表，所以两种都要认
    empty = payload in ([], {}, None) or (isinstance(payload, dict) and payload.get("items") == [])
    return {
        "接口": path,
        "参数": params or {},
        "结果": text[:MAX_API_CHARS] if truncated else payload,
        "说明": (
            "结果太长已截断——请用参数缩小范围（指定日期、加筛选、减小 page_size）"
            if truncated
            else (
                "**空结果**：这个筛选条件下没有数据。换个筛选条件，或先查一下「有哪些日期有数据」"
                "（例如先看菜单或采集记录），别一个日期一个日期地扫"
                if empty
                else "以上是接口原样返回的数据"
            )
        ),
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
    #: 需要知道「现在是谁在问」的读工具（例如以他的身份去调只读接口）
    needs_actor: bool = False


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
    is_breakfast_staple: bool = False,
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
                "早餐固定供应": "是" if is_breakfast_staple else "否",
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
            "is_breakfast_staple": is_breakfast_staple,
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
            is_breakfast_staple=bool(payload.get("is_breakfast_staple")),
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
    "is_breakfast_staple": "早餐固定供应",
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
    is_breakfast_staple: bool | None = None,
    note: str | None = None,
    recipe_items: list[dict[str, Any]] | None = None,
    seasoning_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """修改菜品：基础信息按字段改，配方是**整体替换**（与页面上同一个语义）。"""
    dish = _dish_or_fail(session, name)
    # 值不全是字符串：`is_breakfast_staple` 是布尔，注解不能跟着推断走
    changes: dict[str, Any] = {
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
    # 布尔字段单独处理：`False` 是**要改成的值**，不能被上面那句「空值过滤」吃掉——
    # 否则「取消早餐固定供应」这条指令会静默变成「什么都不改」
    if is_breakfast_staple is not None:
        changes["is_breakfast_staple"] = is_breakfast_staple
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


# ---------------------------------------------------------------------------
# 一句话录一餐：录入采集、调整菜单
# ---------------------------------------------------------------------------
def _resolve_dishes(session: Session, names: list[str]) -> tuple[list[Any], list[str]]:
    """把菜名解析成库里的菜品。对不上的**全部**列出来，而不是只报第一个。"""
    resolved: list[Any] = []
    missing: list[str] = []
    for name in names:
        clean = str(name).strip()
        if not clean:
            continue
        found = dish_service.list_dishes(session, keyword=clean, page=1, page_size=MAX_ROWS)
        matched = next((row for row in found.items if row.name == clean), None)
        if matched is None:
            missing.append(clean)
        else:
            resolved.append(matched)
    return resolved, missing


def _collection_snapshot(
    session: Session, *, on_date: date, meal_type: MealType
) -> dict[str, Any] | None:
    """把这一餐现在的采集记录整份记下来，供撤回时写回。"""
    sheet = collection_service.build_sheet(session, on_date=on_date, meal_type=meal_type)
    if not sheet.saved:
        return None
    return {
        "diner_count": sheet.diner_count,
        "oil_total_g": sheet.oil_total_g,
        "salt_total_g": sheet.salt_total_g,
        "sugar_total_g": sheet.sugar_total_g,
        "leftover_weight_g": sheet.leftover_weight_g,
        "note": sheet.note,
        "anomaly_flags": [row.value for row in sheet.anomaly_flags if not row.system],
        "dishes": [
            {
                "dish_id": row.dish_id,
                "servings_produced": row.servings_produced or "0",
                "leftover_ratio": row.leftover_ratio,
                "leftover_weight_g": row.leftover_weight_g,
                "is_substituted": row.is_substituted,
                "substitution_note": row.substitution_note,
            }
            for row in sheet.dishes
            if row.selected
        ],
    }


def _collection_token(session: Session, *, on_date: date, meal_type: MealType) -> str:
    return publication.digest(
        {
            "record": collection_service.record_token(
                session, on_date=on_date, meal_type=meal_type
            ),
            "menu": publication.meal_state(session, on_date=on_date, meal_type=meal_type),
        }
    )


def _menu_snapshot(session: Session, *, on_date: date, meal_type: MealType) -> list[dict[str, Any]]:
    """菜单日现在有哪几道菜（含计划份数），撤回时按它恢复。"""
    sheet = collection_service.build_sheet(session, on_date=on_date, meal_type=meal_type)
    return [
        {"dish_id": row.dish_id, "planned_servings": row.planned_servings}
        for row in sheet.dishes
        if row.selected
    ]


def save_collection_draft(
    session: Session,
    *,
    diner_count: int,
    dishes: list[dict[str, Any]],
    on_date: str | None = None,
    meal_type: str | None = None,
    oil_total_g: str | None = None,
    salt_total_g: str | None = None,
    sugar_total_g: str | None = None,
    leftover_weight_g: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """「一句话录一餐」：某天某一餐供了哪几道菜、各多少份、多少人次、油盐糖总量。

    这是全系统**影响面最大**的一次写入：人次与油盐糖进看板与人均摄入，份数进预测的历史序列，
    菜品进公开大屏。所以预览要把这些摆全，并说明会被重算什么。
    """
    target = _date_arg(on_date)
    meal = _meal_arg(meal_type)
    resolved, missing = _resolve_dishes(
        session, [str(line.get("dish_name") or "") for line in dishes or []]
    )
    warnings: list[str] = []
    if missing:
        warnings.append("菜品库里没有这几道菜，先确认名字：" + "、".join(missing))
    if not resolved:
        warnings.append("至少要有一道能对上库里菜品的菜，否则这一餐没有可核算的内容")
    if diner_count <= 0:
        warnings.append("就餐人次必须大于 0，人均摄入要靠它才算得出来")
    if collection_service.has_collection(session, on_date=target, meal_type=meal):
        warnings.append(
            f"{target} {meal.label} 已经录过了：这份会**整份覆盖**原来那条，"
            "原来的人次、油盐糖与份数都会被替换"
        )
    warnings.append(
        "保存后会按这一餐重算营养：人均摄入、达标率与浪费率都会跟着变；这一天也会进入预测的历史序列"
    )
    warnings.append("确认之后可以「撤回」，撤回会把这一餐恢复成现在这个样子")

    lines = [
        {
            "菜品": dish.name,
            "出餐份数": str(line.get("servings") or ""),
            "剩余比例": str(line.get("leftover_ratio") or "—"),
        }
        for line, dish in zip(dishes or [], resolved, strict=False)
    ]
    return {
        "title": f"录入采集：{target} {meal.label}",
        "summary": f"把 {target} {meal.label} 的一餐录进去：{len(resolved)} 道菜、{diner_count} 人次",
        "preview": {
            "将录入": {
                "日期": target.isoformat(),
                "餐次": meal.label,
                "就餐人次": diner_count,
                "食用油_克": oil_total_g or "0",
                "食盐_克": salt_total_g or "0",
                "添加糖_克": sugar_total_g or "0",
                "剩餐总重_克": leftover_weight_g or "—",
                "备注": note or "—",
            },
            "菜品": lines,
            "提示": warnings,
        },
        "payload": {
            "on_date": target.isoformat(),
            "expected_collection_token": _collection_token(session, on_date=target, meal_type=meal),
            "meal_type": meal.value,
            "diner_count": diner_count,
            "oil_total_g": oil_total_g or "0",
            "salt_total_g": salt_total_g or "0",
            "sugar_total_g": sugar_total_g or "0",
            "leftover_weight_g": leftover_weight_g,
            "note": note,
            "dishes": [
                {"dish_id": str(dish.id), "line": line}
                for dish, line in zip(resolved, dishes or [], strict=False)
            ],
        },
    }


def save_collection_execute(
    session: Session, payload: dict[str, Any], *, actor: Any, commit: bool = True
) -> ExecutionOutcome:
    """确认之后真正把这一餐写进去，并记下「怎么撤回」。"""
    from app.modules.collection.schemas import DailyLogWrite, LoggedDishWrite

    target = date.fromisoformat(str(payload["on_date"]))
    meal = MealType(str(payload["meal_type"]))
    lock_meal(session, target, meal)
    if (
        not payload.get("expected_collection_token")
        or _collection_token(session, on_date=target, meal_type=meal)
        != payload["expected_collection_token"]
    ):
        raise BusinessRuleError("这餐采集或菜单在预览后又被修改，请重新提议并核对")
    before_menu = publication.meal_state(session, on_date=target, meal_type=meal)
    previous = _collection_snapshot(session, on_date=target, meal_type=meal)
    previous_menu = _menu_snapshot(session, on_date=target, meal_type=meal)

    saved = collection_service.save_sheet(
        session,
        on_date=target,
        payload=DailyLogWrite(
            meal_type=meal,
            diner_count=int(payload["diner_count"]),
            oil_total_g=payload["oil_total_g"],
            salt_total_g=payload["salt_total_g"],
            sugar_total_g=payload["sugar_total_g"],
            leftover_weight_g=payload.get("leftover_weight_g"),
            note=payload.get("note"),
            dishes=[
                LoggedDishWrite(
                    dish_id=item["dish_id"],
                    servings_produced=item["line"].get("servings") or "0",
                    leftover_ratio=item["line"].get("leftover_ratio"),
                )
                for item in payload["dishes"]
            ],
        ),
        actor_id=actor.id,
        commit=False,
    )
    expected = _collection_token(session, on_date=target, meal_type=meal)
    if commit:
        session.commit()
    return ExecutionOutcome(
        result={
            "实体": "采集记录",
            "日期": target.isoformat(),
            "餐次": meal.label,
            "菜品数": saved.dish_count,
            "重算营养结果": saved.nutrition_rows,
        },
        undo=(
            UndoStep(
                tool="restore_collection",
                payload={
                    "on_date": target.isoformat(),
                    "meal_type": meal.value,
                    "previous": previous,
                    "previous_menu": previous_menu,
                    "before_menu": before_menu,
                    "expected_collection_token": expected,
                },
            ),
        ),
    )


def restore_collection_execute(
    session: Session, payload: dict[str, Any], *, actor: Any, commit: bool = True
) -> ExecutionOutcome:
    """撤回一次采集：要么写回原来那条记录，要么把这条误录整份丢掉。"""
    from app.modules.collection.schemas import DailyLogWrite, LoggedDishWrite

    target = date.fromisoformat(str(payload["on_date"]))
    meal = MealType(str(payload["meal_type"]))
    lock_meal(session, target, meal)
    if (
        not payload.get("expected_collection_token")
        or _collection_token(session, on_date=target, meal_type=meal)
        != payload["expected_collection_token"]
    ):
        raise BusinessRuleError("这餐采集或菜单在确认后又被改过，旧卡片不能撤回覆盖，请人工核对")
    previous = payload.get("previous")

    if previous:
        collection_service.save_sheet(
            session,
            on_date=target,
            payload=DailyLogWrite(
                meal_type=meal,
                diner_count=int(previous["diner_count"] or 0),
                oil_total_g=previous["oil_total_g"] or "0",
                salt_total_g=previous["salt_total_g"] or "0",
                sugar_total_g=previous["sugar_total_g"] or "0",
                leftover_weight_g=previous.get("leftover_weight_g"),
                note=previous.get("note"),
                anomaly_flags=previous.get("anomaly_flags") or [],
                dishes=[
                    LoggedDishWrite(
                        dish_id=item["dish_id"],
                        servings_produced=item["servings_produced"],
                        leftover_ratio=item.get("leftover_ratio"),
                        leftover_weight_g=item.get("leftover_weight_g"),
                        is_substituted=item.get("is_substituted", False),
                        substitution_note=item.get("substitution_note"),
                    )
                    for item in previous["dishes"]
                ],
            ),
            actor_id=actor.id,
            commit=False,
        )
        action = "写回原来那条采集记录"
    else:
        collection_service.discard_sheet(
            session,
            on_date=target,
            meal_type=meal,
            actor_id=actor.id,
            commit=False,
            actor_name=actor.display_name,
            audit_note="撤回 AI 助手录入的采集：删掉这条记录",
        )
        action = "删掉这次录入的采集记录"

    publication.restore_menu(
        session,
        on_date=target,
        meal_type=meal,
        before=payload["before_menu"],
        expected_token=publication.digest(
            publication.meal_state(session, on_date=target, meal_type=meal)
        ),
        actor=actor,
        commit=False,
        restoring_collection=True,
    )
    if commit:
        session.commit()
    return ExecutionOutcome(result={"实体": "采集记录", "日期": target.isoformat(), "撤回": action})


def _write_menu(
    session: Session, *, on_date: date, meal_type: MealType, items: list[dict[str, Any]], actor: Any
) -> None:
    menu_service.plan_menu_day(
        session,
        on_date=on_date,
        meal_type=meal_type,
        dishes=[
            menu_service.PlannedDish(
                dish_id=UUID(str(item["dish_id"])),
                planned_servings=(
                    None
                    if item.get("planned_servings") is None
                    else Decimal(str(item["planned_servings"]))
                ),
            )
            for item in items
        ],
        created_by=actor.id,
    )
    session.commit()


def set_menu_day_draft(
    session: Session,
    *,
    dish_names: list[str],
    on_date: str | None = None,
    meal_type: str | None = None,
) -> dict[str, Any]:
    """调整某天某一餐供应哪些菜（菜单日）。

    已经录过采集的日子直接拒绝：那一天的菜单以实际供应为准，要改就改采集单——
    否则会出现「菜单与实际供应对不上」，而营养结果是按菜单算的。
    """
    target = _date_arg(on_date)
    meal = _meal_arg(meal_type)
    if collection_service.has_collection(session, on_date=target, meal_type=meal):
        raise BusinessRuleError(
            f"{target} {meal.label} 已经录过采集了，菜单以实际供应为准；"
            "要改这一餐请用「录入采集」（它会把菜单一起改掉）"
        )
    resolved, missing = _resolve_dishes(session, dish_names)
    warnings: list[str] = []
    if missing:
        warnings.append("菜品库里没有这几道菜：" + "、".join(missing))
    if not resolved:
        warnings.append("至少要有一道能对上库里菜品的菜")
    warnings.append(
        "这是「计划」性质：写进去之后公开大屏当天就会显示，"
        "每日采集页的供应菜品也会按它勾好（录采集时按实际供应覆盖）"
    )
    warnings.append("确认之后可以「撤回」，菜单会恢复成现在这几道菜")
    return {
        "title": f"调整菜单：{target} {meal.label}",
        "summary": f"把 {target} {meal.label} 的菜单改成："
        + "、".join(dish.name for dish in resolved),
        "preview": {
            "将改成": {"日期": target.isoformat(), "餐次": meal.label},
            "菜品": [{"菜品": dish.name, "类别": dish.category_label} for dish in resolved],
            "提示": warnings,
        },
        "payload": {
            "on_date": target.isoformat(),
            "meal_type": meal.value,
            "dish_ids": [str(dish.id) for dish in resolved],
            "expected_menu_token": publication.digest(
                publication.meal_state(session, on_date=target, meal_type=meal)
            ),
        },
    }


def set_menu_day_execute(
    session: Session, payload: dict[str, Any], *, actor: Any, commit: bool = True
) -> ExecutionOutcome:
    target = date.fromisoformat(str(payload["on_date"]))
    meal = MealType(str(payload["meal_type"]))
    lock_meal(session, target, meal)
    before = publication.meal_state(session, on_date=target, meal_type=meal)
    if (
        not payload.get("expected_menu_token")
        or publication.digest(before) != payload["expected_menu_token"]
    ):
        raise BusinessRuleError("菜单在预览后已经变化，或旧卡片缺少版本，请重新提议并确认")
    menu_service.plan_menu_day(
        session,
        on_date=target,
        meal_type=meal,
        dishes=[
            menu_service.PlannedDish(dish_id=UUID(str(value))) for value in payload["dish_ids"]
        ],
        created_by=actor.id,
    )
    nutrition_service.compute_menu_day(session, on_date=target, meal_type=meal)
    after = publication.meal_state(session, on_date=target, meal_type=meal)
    undo = UndoStep(
        tool="restore_menu_day",
        payload={
            "on_date": target.isoformat(),
            "meal_type": meal.value,
            "items": _menu_snapshot_from_state(before),
            "before": before,
            "expected_menu_token": publication.digest(after),
        },
    )
    if commit:
        session.commit()
    return ExecutionOutcome(
        result={
            "实体": "菜单日",
            "日期": target.isoformat(),
            "餐次": meal.label,
            "菜品数": len(payload["dish_ids"]),
        },
        undo=(undo,),
    )


def _menu_snapshot_from_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"dish_id": row[0], "planned_servings": None if row[1] == "None" else row[1]}
        for row in state.get("items", [])
    ]


def restore_menu_day_execute(
    session: Session, payload: dict[str, Any], *, actor: Any, commit: bool = True
) -> ExecutionOutcome:
    target = date.fromisoformat(str(payload["on_date"]))
    meal = MealType(str(payload["meal_type"]))
    if "before" not in payload or not payload.get("expected_menu_token"):
        raise BusinessRuleError("旧的撤回记录缺少菜单版本快照，请人工核对当前菜单")
    publication.restore_menu(
        session,
        on_date=target,
        meal_type=meal,
        before=payload["before"],
        expected_token=payload["expected_menu_token"],
        actor=actor,
        suggestion_id=UUID(payload["suggestion_id"]) if payload.get("suggestion_id") else None,
        commit=commit,
    )
    return ExecutionOutcome(
        result={"实体": "菜单日", "日期": target.isoformat(), "状态": "已恢复成原来的菜单"}
    )


# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# 排菜单：一句话出方案，确认后落到当日数据
# ---------------------------------------------------------------------------
def generate_menu_plan(
    session: Session,
    *,
    on_date: str | None = None,
    meal_type: str | None = None,
    diner_count: int | None = None,
) -> dict[str, Any]:
    """排一份菜单：在营养目标下选菜 → 按历史与日历预测份数 → 算出要买多少料。

    这件事**只出方案**，不改当天的菜单、不进采集：它产出的是一版建议
    （外加一条推荐记录，供页面上再看与采纳）。所以它不需要人确认就能跑——
    真正的写入是另一个工具（`sync_menu_plan`），那个要确认。
    """
    target = _date_arg(on_date)
    meal = _meal_arg(meal_type)
    plan = menuplan_service.build_menu_plan(
        session, on_date=target, meal_type=meal, diner_count=diner_count
    )
    if collection_service.has_collection(session, on_date=target, meal_type=meal):
        # 这一天已经录过采集：方案还能算，但同步不进去（菜单以实际供应为准）
        note = f"注意：{target} {meal.label} 已经录过采集，这一版只能参考，同步不进去"
    else:
        note = "这一版还只是建议：确认之后用 sync_menu_plan 写进当天的当日数据"
    return {
        "日期": target.isoformat(),
        "餐次": meal.label,
        "就餐人次": plan.diner_count,
        "菜品": [
            {
                "菜品": dish.dish_name,
                "类别": dish.category_label,
                "做法": dish.cooking_method_label,
                "预测份数": dish.predicted_servings,
                "预测依据": dish.predicted_basis_label,
                "单份能量_千卡": dish.energy_kcal,
                "单份食盐_克": dish.salt_g,
                "营养取自": dish.nutrition_basis,
            }
            for dish in plan.dishes
        ],
        "与营养目标的差距": [
            {"指标": gap.label, "目标": gap.target_text, "实际": gap.actual, "结论": gap.status}
            for gap in plan.gaps
        ],
        "推荐理由": [reason.text for reason in plan.reasons],
        "采购": {
            "项数": len(plan.requirements),
            "合计金额_元": plan.total_cost,
            "预算_元": plan.budget,
            "明细": [
                {"食材": row.name, "数量_公斤": row.quantity, "金额_元": row.estimated_cost}
                for row in plan.requirements[:10]
            ],
        },
        "规则": plan.servings_note,
        "提示": [*plan.notes, *plan.calendar_notes, note],
    }


def sync_menu_plan_draft(
    session: Session, *, on_date: str | None = None, meal_type: str | None = None
) -> dict[str, Any]:
    """把最近生成的那一版菜单写进当天的当日数据（菜单日 + 营养 + 记为已采纳）。"""
    target = _date_arg(on_date)
    meal = _meal_arg(meal_type)
    suggestion_id = recommendation_service.latest_suggestion_id(
        session, on_date=target, meal_type=meal
    )
    if suggestion_id is None:
        raise BusinessRuleError(
            f"{target} {meal.label} 还没有生成过菜单。先用 generate_menu_plan 排一版，再来同步"
        )
    if collection_service.has_collection(session, on_date=target, meal_type=meal):
        raise BusinessRuleError(
            f"{target} {meal.label} 已经录过采集了，菜单以实际供应为准；"
            "要改这一餐请用「录入采集」那个工具"
        )
    suggestion = recommendation_service.get_suggestion(session, suggestion_id)
    warnings = [
        "这一步会写进当日数据：每日采集页的供应菜品按它勾好，公开大屏当天就会显示它，"
        "并按配方算出这天的单份营养；同时那一版菜单会被记为「已采纳」",
        "确认之后可以「撤回」：菜单恢复成现在这几道菜",
    ]
    return {
        "title": f"同步菜单到当日数据：{target} {meal.label}",
        "summary": f"把最近生成的那一版菜单（{len(suggestion.dishes)} 道菜）写进 {target} {meal.label} 的当日数据",
        "preview": {
            "将写入": {
                "日期": target.isoformat(),
                "餐次": meal.label,
                "菜品数": len(suggestion.dishes),
            },
            "菜品": [
                {"菜品": dish.dish_name, "类别": dish.category_label} for dish in suggestion.dishes
            ],
            "提示": warnings,
        },
        "payload": {
            "on_date": target.isoformat(),
            "meal_type": meal.value,
            "suggestion_id": str(suggestion_id),
        },
    }


def sync_menu_plan_execute(
    session: Session, payload: dict[str, Any], *, actor: Any, commit: bool = True
) -> ExecutionOutcome:
    target = date.fromisoformat(str(payload["on_date"]))
    meal = MealType(str(payload["meal_type"]))
    sid = UUID(str(payload["suggestion_id"]))
    # 与发布一致：先锁建议，再锁餐次；锁内抓取撤回快照。
    from sqlalchemy import select

    from app.modules.recommendation.models import MenuSuggestion

    suggestion = session.scalar(
        select(MenuSuggestion)
        .where(MenuSuggestion.id == sid)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    lock_meal(session, target, meal)
    before = publication.meal_state(session, on_date=target, meal_type=meal)
    already = bool(suggestion and (suggestion.nutrition_gap or {}).get("publication"))
    result = menuplan_service.sync_to_day(
        session, on_date=target, meal_type=meal, suggestion_id=sid, actor_id=actor.id, commit=False
    )
    after = publication.meal_state(session, on_date=target, meal_type=meal)
    # 重复同步只取回执，不能把第一次的已发布菜单当成“撤回前状态”。
    undo = (
        ()
        if already
        else (
            UndoStep(
                tool="restore_menu_day",
                payload={
                    "on_date": target.isoformat(),
                    "meal_type": meal.value,
                    "suggestion_id": str(sid),
                    "items": _menu_snapshot_from_state(before),
                    "before": before,
                    "expected_menu_token": publication.digest(after),
                },
            ),
        )
    )
    if commit:
        session.commit()
    return ExecutionOutcome(
        result={
            "实体": "菜单日",
            "日期": target.isoformat(),
            "餐次": meal.label,
            "菜品数": result.dish_count,
            "营养结果": result.nutrition_rows,
        },
        undo=undo,
    )


def reopen_suggestion_execute(
    session: Session, payload: dict[str, Any], *, actor: Any
) -> ExecutionOutcome:
    """撤回「同步菜单」时把推荐记录改回待确认。只给撤回用。"""
    suggestion = recommendation_service.reopen_suggestion(
        session, suggestion_id=UUID(str(payload["suggestion_id"]))
    )
    return ExecutionOutcome(
        result={"实体": "菜单推荐记录", "id": suggestion.id, "状态": "回到待确认"}
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
        name="call_api",
        label="调只读接口",
        description=(
            "当一个查询现有工具都覆盖不了时用它：按路径调系统里**只读**的 GET 接口"
            "（例如抽样候选、校准系数、节假日日历、推荐历史、按条件翻采集记录）。"
            "只能调只读接口，写操作一律走别的工具（那些会先出方案、要人确认）。"
            "**不确定路径或参数时，先用 list_read_apis 拿到「路径 + 必填/可选参数」再调**——"
            "盲试会一次吃一个参数错误，把轮次预算耗光。"
        ),
        parameters=_schema(
            {
                "path": {
                    "type": "string",
                    "description": "接口路径，例如 /api/v1/nutrition/candidates",
                },
                "params": {
                    "type": "object",
                    "description": '查询参数，例如 {"start": "2026-10-01", "page_size": 20}',
                },
            },
            required=["path"],
        ),
        handler=call_api,
        needs_actor=True,
    ),
    Tool(
        name="list_read_apis",
        label="列只读接口",
        description=(
            "列出所有可以调的只读接口，以及每个接口的必填与可选参数。"
            "准备用 call_api 之前先调它，就能一次调对。"
        ),
        parameters=_schema(
            {"prefix": {"type": "string", "description": "只列路径里含这个片段的，例如 dashboard"}}
        ),
        handler=list_read_apis,
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
                "is_breakfast_staple": {
                    "type": "boolean",
                    "description": "早餐固定供应：勾上之后这道菜每天都是早餐的一部分，且不再出现在午晚餐",
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
                "is_breakfast_staple": {
                    "type": "boolean",
                    "description": "是否早餐固定供应；取消时传 false",
                },
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
    Tool(
        name="generate_menu_plan",
        label="排菜单",
        description=(
            "排一份菜单：在营养目标下选出做哪几道菜 → 按同星期历史与节假日日历预测每道菜做多少份 → "
            "算出要买多少料。用户说「排一下明天的菜单」「今天午饭做什么」时用它。"
            "**早餐是例外**：菜品库里勾了「早餐固定供应」的那几道菜每天照上，"
            "早餐不参与选菜——所以问早餐时会给出固定那几道，这是对的，不是没生效。"
            "**它只出方案，不改当天的菜单**，所以不需要确认就能跑；"
            "**用户明确要「排/定」菜单时，紧接着调 sync_menu_plan 把确认卡片直接摆出来**，"
            "别让他再说一句「同步」；只是随口问「明天吃什么」时就不用跟着调。"
        ),
        parameters=_schema(
            {
                "on_date": {"type": "string", "description": "日期 YYYY-MM-DD，默认今天"},
                "meal_type": {"type": "string", "description": "餐次：BREAKFAST / LUNCH / DINNER"},
                "diner_count": {
                    "type": "integer",
                    "description": "就餐人次；不填则用最近一次采集的人次",
                },
            }
        ),
        handler=generate_menu_plan,
    ),
    Tool(
        name="sync_menu_plan",
        label="同步菜单到当日数据",
        description=(
            "把最近生成的那一版菜单写进某天某一餐的当日数据：采集页的供应菜品按它勾好、"
            "公开大屏当天就显示、并按配方算出那天的单份营养，同时记为「已采纳」。"
            "**写操作：调用只生成待确认的方案**，确认后才执行；确认后可撤回。"
            "已经录过采集的日子会被拒绝（菜单以实际供应为准）。"
            "**通常紧跟在 generate_menu_plan 之后调用**——用户要「排菜单」时，"
            "排完就把这张确认卡片摆出来，别让他再多说一句。"
        ),
        parameters=_schema(
            {
                "on_date": {"type": "string", "description": "日期 YYYY-MM-DD，默认今天"},
                "meal_type": {"type": "string", "description": "餐次"},
            }
        ),
        read_only=False,
        build_draft=sync_menu_plan_draft,
        execute=sync_menu_plan_execute,
    ),
    Tool(
        name="reopen_suggestion",
        label="推荐记录改回待确认",
        description="撤回「同步菜单」时用。不直接暴露给模型。",
        parameters=_schema({"suggestion_id": {"type": "string"}}, required=["suggestion_id"]),
        read_only=False,
        build_draft=lambda session, **kwargs: kwargs,
        execute=reopen_suggestion_execute,
        hidden=True,
    ),
    Tool(
        name="save_collection",
        label="录入采集",
        description=(
            "录入某一天某一餐的采集数据：供应了哪几道菜、各出餐多少份、就餐人次、"
            "油盐糖的实际投放量与剩餐量。**写操作：调用只生成待确认的方案**，"
            "方案里会写明要录什么、会重算哪些指标；确认后才写库。"
            "这是影响面最大的一次写入——人次与油盐糖进看板，份数进预测的历史序列，菜品进公开大屏。"
            "用户说「今天午餐做了……」「帮我录一下昨天晚饭」时用它。菜名要先能对上菜品库。"
        ),
        parameters=_schema(
            {
                "on_date": {"type": "string", "description": "日期 YYYY-MM-DD，默认今天"},
                "meal_type": {"type": "string", "description": "餐次：BREAKFAST / LUNCH / DINNER"},
                "diner_count": {"type": "integer", "description": "就餐人次"},
                "dishes": {
                    "type": "array",
                    "description": "这一餐供应的菜与出餐份数",
                    "items": {
                        "type": "object",
                        "properties": {
                            "dish_name": {"type": "string"},
                            "servings": {"type": "string", "description": "出餐份数"},
                            "leftover_ratio": {
                                "type": "string",
                                "description": "剩余比例 0~1，可选",
                            },
                        },
                        "required": ["dish_name", "servings"],
                    },
                },
                "oil_total_g": {"type": "string", "description": "当日食用油投放量（克）"},
                "salt_total_g": {"type": "string", "description": "当日食盐投放量（克）"},
                "sugar_total_g": {"type": "string", "description": "当日添加糖投放量（克）"},
                "leftover_weight_g": {"type": "string", "description": "剩餐总重（克）"},
                "note": {"type": "string"},
            },
            required=["diner_count", "dishes"],
        ),
        read_only=False,
        build_draft=save_collection_draft,
        execute=save_collection_execute,
    ),
    Tool(
        name="set_menu_day",
        label="调整菜单",
        description=(
            "把某一天某一餐的菜单改成指定的几道菜（计划性质：公开大屏与采集页都会按它走）。"
            "**写操作：调用只生成待确认的方案**。已经录过采集的日子会被拒绝——"
            "那一天的菜单以实际供应为准，要改用「录入采集」。"
        ),
        parameters=_schema(
            {
                "on_date": {"type": "string", "description": "日期 YYYY-MM-DD，默认今天"},
                "meal_type": {"type": "string", "description": "餐次"},
                "dish_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "这一餐要供应的菜品名称（整份替换）",
                },
            },
            required=["dish_names"],
        ),
        read_only=False,
        build_draft=set_menu_day_draft,
        execute=set_menu_day_execute,
    ),
    Tool(
        name="restore_collection",
        label="撤回一次采集",
        description="撤回「录入采集」时用：写回原来那条记录，或整份丢掉这次误录。不直接暴露给模型。",
        parameters=_schema(
            {
                "on_date": {"type": "string"},
                "meal_type": {"type": "string"},
                "previous": {"type": "object"},
                "previous_menu": {"type": "array"},
            },
            required=["on_date", "meal_type"],
        ),
        read_only=False,
        build_draft=lambda session, **kwargs: kwargs,
        execute=restore_collection_execute,
        hidden=True,
    ),
    Tool(
        name="restore_menu_day",
        label="撤回菜单调整",
        description="撤回「调整菜单」时用。不直接暴露给模型。",
        parameters=_schema(
            {
                "on_date": {"type": "string"},
                "meal_type": {"type": "string"},
                "items": {"type": "array"},
            },
            required=["on_date", "meal_type"],
        ),
        read_only=False,
        build_draft=lambda session, **kwargs: kwargs,
        execute=restore_menu_day_execute,
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

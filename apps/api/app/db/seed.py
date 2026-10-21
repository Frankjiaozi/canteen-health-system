"""种子数据脚本。

用法：

    pnpm db:seed

## 幂等设计

所有实体都以「自然键 → 确定性 UUID」（uuid5）作为主键，并逐字段比对后才决定是否写库。
因此脚本可以随时重跑：第二次执行不会新增任何行，也不会产生无意义的 UPDATE。

## 关于内置营养数值

食材与调味料的五项营养成分、可食部比例**不写在本文件里**，统一取自
`app/db/nutrition_reference.json`——那是从「食物营养成分查询平台」
（中国疾病预防控制中心营养与健康所）逐条取数后落盘的快照，随仓库提交。

取数与校验的工具是 `apps/api/tools/nutrition_reference.py`（`pnpm nutrition:fetch`
/ `pnpm nutrition:verify`），映射表（我方食材 → 平台条目 ID）在
`apps/api/tools/nutrition_sources.json`。**运行期不联网**：第三方站点改版、限流、下线
都不会影响系统；而每一条数值都能回溯到具体条目（`source_version`）与换算过程（`note`）。

本文件只维护「我们自己的东西」：业务名、类别、单价。单价平台没有，
仍是演示值（元/公斤市品），会在备注里单独说明。
"""

from __future__ import annotations

import json
import os
import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, NamedTuple
from uuid import UUID, uuid5

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.security import hash_password, verify_password
from app.db.session import get_session_factory
from app.modules.auth.models import User
from app.modules.collection.models import DailyLog, DailyLogItem
from app.modules.dish.models import Dish, RecipeItem, RecipeSeasoning
from app.modules.forecast.models import Holiday
from app.modules.ingredient.models import Ingredient
from app.modules.menu.models import MenuDay, MenuDayItem
from app.modules.nutrition.models import DishNutrition, NutritionStandard
from app.modules.seasoning.models import Seasoning
from app.shared.enums import (
    CookingMethod,
    DishCategory,
    HolidayKind,
    IngredientCategory,
    MealType,
    SeasoningCategory,
    StandardCode,
    StandardPeriod,
    UserRole,
)

logger = get_logger("app.seed")

# 固定命名空间：保证同一自然键在任何机器、任何时间都得到同一个 UUID
SEED_NAMESPACE = UUID("07b0f0a6-6f2e-4f2b-9a2f-4c2a1b3d5e70")

# 演示账号口令。部署到真实环境前请通过该环境变量覆盖
DEFAULT_DEMO_PASSWORD = "canteen@2026"

# 演示数据的来源标注：明确写成待核对，不伪造权威出处
DEMO_DATA_SOURCE = "演示占位值，待核对"
DEMO_SOURCE_VERSION = "未核对"

#: 历史天数。取 8 周（56 天）的理由：同星期移动平均的可靠程度取决于
#: 「同一个星期几」有多少样本，8 周让每个星期几有 8 个点，同时还能留出
#: 两周做回测。数据量对 PostgreSQL 来说是噪声级别，代价可以忽略。
HISTORY_DAYS = 56


def _stable_id(kind: str, key: str) -> UUID:
    """自然键 → 确定性 UUID。同一 key 永远得到同一 id，这是幂等的基础。"""
    return uuid5(SEED_NAMESPACE, f"{kind}:{key}")


def _upsert(session: Session, model: Any, entity_id: UUID, **values: Any) -> str:
    """按主键写库；已存在时只更新真正变化的字段。

    返回 "created" / "updated" / "unchanged"，供脚本汇总输出——
    重跑时应当全部是 "unchanged"，这就是幂等的可见证据。
    """
    existing = session.get(model, entity_id)
    if existing is None:
        session.add(model(id=entity_id, **values))
        return "created"

    changed = [field for field, value in values.items() if getattr(existing, field) != value]
    for field in changed:
        setattr(existing, field, values[field])
    return "updated" if changed else "unchanged"


def _upsert_by(session: Session, model: Any, natural_key: dict[str, Any], **values: Any) -> str:
    """按自然键（例如「菜品 + 食材」）写入。

    配方行可能在界面上被整体替换过，那时主键已经换了；只有自然键还靠得住。
    种子脚本要能把演示库收敛到当前定义，就必须按自然键找行。
    """
    conditions = [getattr(model, field) == value for field, value in natural_key.items()]
    existing = session.scalar(select(model).where(*conditions))
    if existing is None:
        session.add(model(**natural_key, **values))
        return "created"

    changed = [field for field, value in values.items() if getattr(existing, field) != value]
    for field in changed:
        setattr(existing, field, values[field])
    return "updated" if changed else "unchanged"


def _existing_id(session: Session, model: Any, natural_key: dict[str, Any]) -> UUID | None:
    """按自然键查已有行的主键。

    种子主要按固定主键写（这样重跑幂等），但**固定主键插不进去**的情况是存在的：
    数据库对「日期 + 餐次」这类组合有唯一约束，而这一行可能是别的来源先写下的
    （开发库里手录过、端到端用例录过）。这时按自然键认领它、再收敛到种子定义，
    比硬插一个会撞约束的新行正确。
    """
    conditions = [getattr(model, field) == value for field, value in natural_key.items()]
    return session.scalar(select(model.id).where(*conditions))


class _Tally:
    """统计各类实体的写入结果。"""

    def __init__(self) -> None:
        self.counts: dict[str, dict[str, int]] = {}

    def add(self, entity: str, action: str) -> None:
        bucket = self.counts.setdefault(entity, {"created": 0, "updated": 0, "unchanged": 0})
        bucket[action] += 1

    def report(self) -> str:
        lines = []
        for entity, bucket in self.counts.items():
            total = sum(bucket.values())
            lines.append(
                f"  {entity:<22} 合计 {total:>4}  "
                f"(新增 {bucket['created']}, 更新 {bucket['updated']}, 未变 {bucket['unchanged']})"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 账号
# ---------------------------------------------------------------------------
_ACCOUNTS: list[tuple[str, str, UserRole]] = [
    ("recorder", "王芳（录入员）", UserRole.RECORDER),
    ("canteen", "李强（食堂管理员）", UserRole.CANTEEN_ADMIN),
    ("school", "张敏（学校管理方）", UserRole.SCHOOL_ADMIN),
]


def seed_users(session: Session, tally: _Tally) -> dict[str, UUID]:
    """创建三个可登录角色的演示账号。

    系统内没有学生账号——需求文档里的「学生端」对应的是免登录的公开大屏。
    """
    password = os.environ.get("SEED_DEMO_PASSWORD") or DEFAULT_DEMO_PASSWORD
    ids: dict[str, UUID] = {}

    for username, display_name, role in _ACCOUNTS:
        entity_id = _stable_id("user", username)
        ids[username] = entity_id
        existing = session.get(User, entity_id)
        if existing is None:
            session.add(
                User(
                    id=entity_id,
                    username=username,
                    display_name=display_name,
                    role=role,
                    password_hash=hash_password(password),
                    is_active=True,
                )
            )
            tally.add("用户", "created")
            continue

        action = _upsert(
            session,
            User,
            entity_id,
            username=username,
            display_name=display_name,
            role=role,
            is_active=True,
        )
        # 口令哈希每次生成都带新的随机盐，不能用「逐字段比对」判断是否变化；
        # 只有在演示口令确实对不上时才重置，保证重跑不会产生无意义的 UPDATE
        if not verify_password(password, existing.password_hash):
            existing.password_hash = hash_password(password)
            action = "updated"
        tally.add("用户", action)
    session.flush()
    return ids


# ---------------------------------------------------------------------------
# 营养数据的来源：平台快照
# ---------------------------------------------------------------------------
# 从「食物营养成分查询平台」（中国疾控中心营养与健康所）逐条取数、审过一遍之后
# 落盘的快照。它随仓库提交，**运行期不联网**——第三方站点改版、限流、下线都不影响
# 系统；而每一条数值都能顺着 source_version 回溯到具体条目、顺着 note 回溯换算过程。
NUTRITION_REFERENCE_PATH = Path(__file__).with_name("nutrition_reference.json")

#: 数据来源标注：写进每一条食材与调味料，界面上点得开、看得见
PLATFORM_DATA_SOURCE = "中国食物成分表·食物营养成分查询平台（中国疾控中心营养与健康所）"


def _load_nutrition_reference() -> dict[str, Any]:
    with NUTRITION_REFERENCE_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


_NUTRITION_REFERENCE = _load_nutrition_reference()
_NUTRITION_ITEMS: dict[str, dict[str, Any]] = _NUTRITION_REFERENCE["items"]
_NUTRITION_QUERIED_AT: str = _NUTRITION_REFERENCE["source"]["queried_at"]


def _optional_decimal(raw: str | None) -> Decimal | None:
    """快照里的 null 表示平台未检测——落库为 NULL 而不是 0，写 0 会静默失真。"""
    return None if raw is None else Decimal(raw)


def _nutrition_values(key: str, *, include_edible_ratio: bool = True) -> dict[str, Any]:
    """把快照里的一条记录转成模型字段。

    平台上没有对应条目的（目前只有蚝油）如实退回「演示占位值，待核对」：
    宁可标着待核对，也不编一个看起来权威的出处。
    """
    record = _NUTRITION_ITEMS.get(key)
    if record is None:
        return {
            "data_source": DEMO_DATA_SOURCE,
            "source_version": DEMO_SOURCE_VERSION,
            "note": "平台无对应条目，保留人工维护的演示值；单价同为演示值（元/公斤市品），待核价",
        }

    note_parts = [f"能量原始值 {record['energy_kj']} kJ（1 kcal = 4.184 kJ 换算）"]
    if record["zero_filled"]:
        listed = "、".join(record["zero_filled"])
        note_parts.append(f"平台未列 {listed}，按该物质不含该成分记 0")
    note_parts.append(f"查询日期 {_NUTRITION_QUERIED_AT}")
    note_parts.append("单价为演示值（元/公斤市品），待核价")

    values: dict[str, Any] = {
        "energy_kcal": Decimal(record["energy_kcal"]),
        "protein_g": _optional_decimal(record["protein_g"]),
        "fat_g": _optional_decimal(record["fat_g"]),
        "carb_g": _optional_decimal(record["carb_g"]),
        "sodium_mg": _optional_decimal(record["sodium_mg"]),
        "data_source": PLATFORM_DATA_SOURCE,
        "source_version": f"{record['entry_name']} · 条目 {record['food_id']}",
        "note": "；".join(note_parts),
    }
    if include_edible_ratio:
        values["edible_ratio"] = Decimal(record["edible_ratio"])
    return values


# ---------------------------------------------------------------------------
# 食材
# ---------------------------------------------------------------------------
class _IngredientRow(NamedTuple):
    key: str
    name: str
    category: IngredientCategory
    unit_price: str


# 营养值与可食部不写在这里：统一从 nutrition_reference.json 取，见 _nutrition_values()。
# 这里只维护「我们自己的东西」——业务名、类别、单价（元/公斤市品，演示值）。
_INGREDIENTS: list[_IngredientRow] = [
    _IngredientRow("rice", "大米", IngredientCategory.GRAIN, "5.60"),
    _IngredientRow("flour", "小麦粉", IngredientCategory.GRAIN, "4.20"),
    _IngredientRow("potato", "马铃薯", IngredientCategory.GRAIN, "3.00"),
    _IngredientRow("cabbage", "大白菜", IngredientCategory.VEGETABLE, "1.60"),
    _IngredientRow("broccoli", "西兰花", IngredientCategory.VEGETABLE, "6.00"),
    _IngredientRow("tomato", "番茄", IngredientCategory.VEGETABLE, "4.50"),
    _IngredientRow("cucumber", "黄瓜", IngredientCategory.VEGETABLE, "3.60"),
    _IngredientRow("carrot", "胡萝卜", IngredientCategory.VEGETABLE, "3.20"),
    _IngredientRow("green_pepper", "青椒", IngredientCategory.VEGETABLE, "5.00"),
    _IngredientRow("onion", "洋葱", IngredientCategory.VEGETABLE, "3.40"),
    _IngredientRow("bok_choy", "油菜", IngredientCategory.VEGETABLE, "3.80"),
    _IngredientRow("wood_ear", "木耳（干）", IngredientCategory.FUNGUS_ALGAE, "32.00"),
    _IngredientRow("nori", "紫菜（干）", IngredientCategory.FUNGUS_ALGAE, "40.00"),
    _IngredientRow("egg", "鸡蛋", IngredientCategory.EGG, "9.60"),
    _IngredientRow("pork_lean", "猪肉（瘦）", IngredientCategory.LIVESTOCK_POULTRY, "26.00"),
    _IngredientRow("chicken_breast", "鸡胸肉", IngredientCategory.LIVESTOCK_POULTRY, "18.00"),
    _IngredientRow("beef_lean", "牛肉（瘦）", IngredientCategory.LIVESTOCK_POULTRY, "62.00"),
    _IngredientRow("prawn", "对虾", IngredientCategory.AQUATIC, "45.00"),
    _IngredientRow("tofu", "豆腐（北）", IngredientCategory.BEAN, "5.20"),
    _IngredientRow("apple", "苹果", IngredientCategory.FRUIT, "7.00"),
    _IngredientRow("milk", "牛奶", IngredientCategory.DAIRY, "8.00"),
    _IngredientRow("sesame_oil", "芝麻油", IngredientCategory.OIL_FAT, "26.00"),
    _IngredientRow("pork_belly", "猪肉（五花）", IngredientCategory.LIVESTOCK_POULTRY, "24.00"),
    _IngredientRow("chicken_leg", "鸡腿肉", IngredientCategory.LIVESTOCK_POULTRY, "16.00"),
    _IngredientRow("pork_rib", "猪大排", IngredientCategory.LIVESTOCK_POULTRY, "38.00"),
    _IngredientRow("sea_bass", "鲈鱼", IngredientCategory.AQUATIC, "32.00"),
    _IngredientRow("peanut", "花生仁（炒）", IngredientCategory.NUT, "12.00"),
    _IngredientRow("garlic", "大蒜", IngredientCategory.VEGETABLE, "9.00"),
    _IngredientRow("green_bean", "四季豆", IngredientCategory.VEGETABLE, "7.00"),
    _IngredientRow("winter_melon", "冬瓜", IngredientCategory.VEGETABLE, "3.00"),
]


def seed_ingredients(session: Session, tally: _Tally) -> dict[str, UUID]:
    ids: dict[str, UUID] = {}
    for row in _INGREDIENTS:
        entity_id = _stable_id("ingredient", row.key)
        ids[row.key] = entity_id
        tally.add(
            "食材",
            _upsert(
                session,
                Ingredient,
                entity_id,
                name=row.name,
                category=row.category,
                **_nutrition_values(row.key),
                unit_price=Decimal(row.unit_price),
                is_active=True,
            ),
        )
    session.flush()
    return ids


# ---------------------------------------------------------------------------
# 调味料
# ---------------------------------------------------------------------------
class _SeasoningRow(NamedTuple):
    key: str
    name: str
    category: SeasoningCategory
    unit_price: str


# 每 100 克计，与食材库同一口径，便于统一计算。营养值同样取自平台快照。
_SEASONINGS: list[_SeasoningRow] = [
    _SeasoningRow("soybean_oil", "大豆油", SeasoningCategory.EDIBLE_OIL, "12.00"),
    _SeasoningRow("salt", "食盐", SeasoningCategory.SALT, "2.50"),
    _SeasoningRow("sugar", "白砂糖", SeasoningCategory.SUGAR, "6.00"),
    _SeasoningRow("soy_sauce", "生抽酱油", SeasoningCategory.SOY_SAUCE, "8.00"),
    _SeasoningRow("oyster_sauce", "蚝油", SeasoningCategory.OYSTER_SAUCE, "10.00"),
    _SeasoningRow("corn_starch", "玉米淀粉", SeasoningCategory.STARCH, "7.00"),
    _SeasoningRow("bean_paste", "豆瓣酱", SeasoningCategory.OTHER, "12.00"),
    _SeasoningRow("vinegar", "陈醋", SeasoningCategory.OTHER, "5.00"),
]


def seed_seasonings(session: Session, tally: _Tally) -> dict[str, UUID]:
    ids: dict[str, UUID] = {}
    for row in _SEASONINGS:
        entity_id = _stable_id("seasoning", row.key)
        ids[row.key] = entity_id
        tally.add(
            "调味料",
            _upsert(
                session,
                Seasoning,
                entity_id,
                name=row.name,
                category=row.category,
                unit="g",
                **_nutrition_values(row.key, include_edible_ratio=False),
                unit_price=Decimal(row.unit_price),
                is_active=True,
            ),
        )
    session.flush()
    return ids


# ---------------------------------------------------------------------------
# 菜品与配方
# ---------------------------------------------------------------------------
class _DishRow(NamedTuple):
    key: str
    name: str
    category: DishCategory
    cooking_method: CookingMethod
    standard_serving_g: str
    servings_per_pot: str
    allergens: list[str]
    # (食材 key, 单份用量克, 可食部比例覆盖)
    items: list[tuple[str, str, str | None]]
    # (调味料 key, 单份用量克)
    seasonings: list[tuple[str, str]]
    # 早餐固定供应：这些菜构成每天的早餐，不参与午晚餐的选菜
    is_breakfast_staple: bool = False


_DISHES: list[_DishRow] = [
    _DishRow(
        "tomato_egg",
        "番茄炒蛋",
        DishCategory.HALF_MEAT,
        CookingMethod.STIR_FRY,
        "150.00",
        "40.00",
        ["蛋"],
        [("tomato", "80.000", None), ("egg", "60.000", None)],
        [("soybean_oil", "6.000"), ("salt", "1.200"), ("sugar", "1.500")],
    ),
    _DishRow(
        "stir_broccoli",
        "清炒西兰花",
        DishCategory.VEGETABLE,
        CookingMethod.STIR_FRY,
        "120.00",
        "40.00",
        [],
        [("broccoli", "110.000", None), ("carrot", "15.000", None)],
        [("soybean_oil", "5.000"), ("salt", "1.000")],
    ),
    _DishRow(
        "beef_potato",
        "土豆炖牛肉",
        DishCategory.MEAT,
        CookingMethod.STEW,
        "180.00",
        "35.00",
        [],
        [
            ("beef_lean", "70.000", None),
            ("potato", "80.000", None),
            ("onion", "20.000", None),
            ("carrot", "15.000", None),
        ],
        [
            ("soybean_oil", "4.000"),
            ("salt", "1.500"),
            ("soy_sauce", "4.000"),
            ("corn_starch", "1.500"),
        ],
    ),
    _DishRow(
        "nori_egg_soup",
        "紫菜蛋花汤",
        DishCategory.SOUP,
        CookingMethod.BOIL,
        "220.00",
        "60.00",
        ["蛋"],
        [("nori", "3.000", None), ("egg", "15.000", None)],
        [("salt", "0.800"), ("soybean_oil", "1.000")],
    ),
    _DishRow(
        "steamed_rice",
        "米饭",
        DishCategory.STAPLE,
        CookingMethod.STEAM,
        "200.00",
        "80.00",
        [],
        [("rice", "80.000", None)],
        [],
    ),
    _DishRow(
        "steamed_bun",
        "馒头",
        DishCategory.STAPLE,
        CookingMethod.STEAM,
        "100.00",
        "100.00",
        ["小麦"],
        [("flour", "85.000", None)],
        [("sugar", "2.000")],
    ),
    _DishRow(
        "tomato_egg_soup",
        "番茄蛋汤",
        DishCategory.SOUP,
        CookingMethod.BOIL,
        "220.00",
        "60.00",
        ["蛋"],
        [("tomato", "30.000", None), ("egg", "12.000", None)],
        [("salt", "0.800"), ("soybean_oil", "0.800")],
    ),
    _DishRow(
        "winter_melon_rib_soup",
        "冬瓜排骨汤",
        DishCategory.SOUP,
        CookingMethod.STEW,
        "260.00",
        "50.00",
        [],
        [("winter_melon", "60.000", None), ("pork_rib", "30.000", None)],
        [("salt", "1.000")],
    ),
    _DishRow(
        "braised_pork",
        "红烧肉",
        DishCategory.MEAT,
        CookingMethod.STEW,
        "120.00",
        "30.00",
        [],
        [("pork_belly", "90.000", None), ("potato", "20.000", None)],
        [
            ("soybean_oil", "3.000"),
            ("salt", "1.200"),
            ("sugar", "6.000"),
            ("soy_sauce", "5.000"),
        ],
    ),
    _DishRow(
        "chicken_potato",
        "鸡腿烧土豆",
        DishCategory.MEAT,
        CookingMethod.STEW,
        "180.00",
        "35.00",
        [],
        [
            ("chicken_leg", "90.000", None),
            ("potato", "60.000", None),
            ("onion", "15.000", None),
        ],
        [
            ("soybean_oil", "4.000"),
            ("salt", "1.500"),
            ("soy_sauce", "4.000"),
            ("corn_starch", "1.500"),
        ],
    ),
    _DishRow(
        "steamed_bass",
        "清蒸鲈鱼",
        DishCategory.MEAT,
        CookingMethod.STEAM,
        "130.00",
        "20.00",
        ["鱼"],
        [("sea_bass", "120.000", None)],
        [("soybean_oil", "3.000"), ("salt", "1.000"), ("soy_sauce", "5.000")],
    ),
    _DishRow(
        "kungpao_chicken",
        "宫保鸡丁",
        DishCategory.MEAT,
        CookingMethod.STIR_FRY,
        "150.00",
        "35.00",
        ["花生"],
        [
            ("chicken_breast", "70.000", None),
            ("peanut", "12.000", None),
            ("cucumber", "30.000", None),
            ("carrot", "20.000", None),
        ],
        [
            ("soybean_oil", "5.000"),
            ("salt", "1.200"),
            ("sugar", "4.000"),
            ("soy_sauce", "5.000"),
            ("corn_starch", "2.000"),
        ],
    ),
    _DishRow(
        "wood_ear_pork",
        "木耳炒肉片",
        DishCategory.HALF_MEAT,
        CookingMethod.STIR_FRY,
        "140.00",
        "35.00",
        [],
        [
            ("wood_ear", "4.000", None),
            ("pork_lean", "55.000", None),
            ("green_pepper", "25.000", None),
        ],
        [("soybean_oil", "5.000"), ("salt", "1.200"), ("soy_sauce", "4.000")],
    ),
    _DishRow(
        "mapo_tofu",
        "麻婆豆腐",
        DishCategory.HALF_MEAT,
        CookingMethod.STEW,
        "150.00",
        "35.00",
        ["大豆"],
        [("tofu", "110.000", None), ("pork_lean", "25.000", None)],
        [
            ("soybean_oil", "6.000"),
            ("salt", "1.000"),
            ("bean_paste", "6.000"),
            ("corn_starch", "2.000"),
        ],
    ),
    _DishRow(
        "pepper_pork",
        "青椒炒肉丝",
        DishCategory.HALF_MEAT,
        CookingMethod.STIR_FRY,
        "140.00",
        "35.00",
        [],
        [("green_pepper", "70.000", None), ("pork_lean", "50.000", None)],
        [("soybean_oil", "5.000"), ("salt", "1.200"), ("soy_sauce", "4.000")],
    ),
    _DishRow(
        "carrot_egg",
        "胡萝卜炒鸡蛋",
        DishCategory.HALF_MEAT,
        CookingMethod.STIR_FRY,
        "140.00",
        "40.00",
        ["蛋"],
        [("carrot", "70.000", None), ("egg", "50.000", None)],
        [("soybean_oil", "5.000"), ("salt", "1.000")],
    ),
    _DishRow(
        "garlic_bok_choy",
        "蒜蓉油菜",
        DishCategory.VEGETABLE,
        CookingMethod.STIR_FRY,
        "130.00",
        "40.00",
        [],
        [("bok_choy", "110.000", None), ("garlic", "5.000", None)],
        [("soybean_oil", "5.000"), ("salt", "1.000")],
    ),
    _DishRow(
        "vinegar_cabbage",
        "醋溜白菜",
        DishCategory.VEGETABLE,
        CookingMethod.STIR_FRY,
        "130.00",
        "40.00",
        [],
        [("cabbage", "120.000", None)],
        [
            ("soybean_oil", "5.000"),
            ("salt", "1.000"),
            ("vinegar", "5.000"),
            ("sugar", "3.000"),
        ],
    ),
    _DishRow(
        "cucumber_salad",
        "凉拌黄瓜",
        DishCategory.VEGETABLE,
        CookingMethod.COLD_DRESS,
        "120.00",
        "40.00",
        [],
        [("cucumber", "110.000", None)],
        [
            ("salt", "1.000"),
            ("vinegar", "4.000"),
            ("soybean_oil", "2.000"),
            ("sugar", "2.000"),
        ],
    ),
    _DishRow(
        "dry_fried_beans",
        "干煸豆角",
        DishCategory.VEGETABLE,
        CookingMethod.STIR_FRY,
        "120.00",
        "35.00",
        [],
        [("green_bean", "110.000", None)],
        [("soybean_oil", "7.000"), ("salt", "1.200"), ("bean_paste", "4.000")],
    ),
    _DishRow(
        "winter_melon_egg_soup",
        "冬瓜蛋花汤",
        DishCategory.SOUP,
        CookingMethod.BOIL,
        "220.00",
        "60.00",
        ["蛋"],
        [("winter_melon", "80.000", None), ("egg", "12.000", None)],
        [("salt", "0.700"), ("soybean_oil", "0.800")],
    ),
    _DishRow(
        "tomato_tofu_soup",
        "番茄豆腐汤",
        DishCategory.SOUP,
        CookingMethod.BOIL,
        "220.00",
        "60.00",
        ["大豆"],
        [("tomato", "35.000", None), ("tofu", "40.000", None)],
        [("salt", "0.800"), ("soybean_oil", "0.800")],
    ),
    _DishRow(
        "nori_tofu_soup",
        "紫菜豆腐汤",
        DishCategory.SOUP,
        CookingMethod.BOIL,
        "220.00",
        "60.00",
        ["大豆"],
        [("nori", "3.000", None), ("tofu", "45.000", None)],
        [("salt", "0.700"), ("soybean_oil", "0.800")],
    ),
    _DishRow(
        "garlic_broccoli",
        "蒜蓉西兰花",
        DishCategory.VEGETABLE,
        CookingMethod.STIR_FRY,
        "130.00",
        "40.00",
        [],
        [("broccoli", "110.000", None), ("garlic", "5.000", None)],
        [("soybean_oil", "5.000"), ("salt", "1.000")],
    ),
    _DishRow(
        "pepper_potato",
        "青椒土豆丝",
        DishCategory.VEGETABLE,
        CookingMethod.STIR_FRY,
        "130.00",
        "40.00",
        [],
        [("green_pepper", "40.000", None), ("potato", "80.000", None)],
        [("soybean_oil", "5.000"), ("salt", "1.200"), ("vinegar", "2.000")],
    ),
    _DishRow(
        "onion_wood_ear",
        "洋葱木耳",
        DishCategory.VEGETABLE,
        CookingMethod.STIR_FRY,
        "120.00",
        "40.00",
        [],
        [("onion", "60.000", None), ("wood_ear", "3.000", None)],
        [("soybean_oil", "4.000"), ("salt", "1.000"), ("soy_sauce", "2.000")],
    ),
    _DishRow(
        "carrot_stir",
        "清炒胡萝卜",
        DishCategory.VEGETABLE,
        CookingMethod.STIR_FRY,
        "120.00",
        "40.00",
        [],
        [("carrot", "110.000", None), ("garlic", "3.000", None)],
        [("soybean_oil", "4.000"), ("salt", "0.800")],
    ),
    _DishRow(
        "tomato_beef",
        "番茄炖牛肉",
        DishCategory.MEAT,
        CookingMethod.STEW,
        "180.00",
        "35.00",
        [],
        [
            ("beef_lean", "70.000", None),
            ("tomato", "60.000", None),
            ("onion", "15.000", None),
        ],
        [("soybean_oil", "3.000"), ("salt", "1.200"), ("soy_sauce", "3.000")],
    ),
    _DishRow(
        "chicken_cucumber",
        "鸡丁炒黄瓜",
        DishCategory.HALF_MEAT,
        CookingMethod.STIR_FRY,
        "140.00",
        "35.00",
        [],
        [("chicken_breast", "60.000", None), ("cucumber", "50.000", None)],
        [
            ("soybean_oil", "5.000"),
            ("salt", "1.000"),
            ("soy_sauce", "3.000"),
            ("corn_starch", "1.000"),
        ],
    ),
    _DishRow(
        "prawn_tofu",
        "虾仁豆腐",
        DishCategory.HALF_MEAT,
        CookingMethod.STEW,
        "150.00",
        "35.00",
        ["虾", "大豆"],
        [("prawn", "40.000", None), ("tofu", "80.000", None)],
        [
            ("soybean_oil", "3.000"),
            ("salt", "1.000"),
            ("soy_sauce", "3.000"),
            ("corn_starch", "1.500"),
        ],
    ),
    # ---- 早餐 ----
    #
    # 早餐不走推荐求解：学校早饭就是每天固定那几样，把它当成「待优化的选择」
    # 既不符合现实，也会和午晚餐用同一套目标算出同一份菜单。这几道菜勾上
    # `is_breakfast_staple`，构成每天的早餐，同时不再进入午晚餐的候选池。
    _DishRow(
        "congee",
        "白粥",
        DishCategory.STAPLE,
        CookingMethod.BOIL,
        "300.00",
        "80.00",
        [],
        [("rice", "60.000", None)],
        [],
        is_breakfast_staple=True,
    ),
    _DishRow(
        "steamed_roll",
        "花卷",
        DishCategory.STAPLE,
        CookingMethod.STEAM,
        "80.00",
        "100.00",
        ["小麦"],
        [("flour", "70.000", None)],
        # 刻意不加烹调油：蒸制在 `_OIL_BIAS_BY_METHOD` 里的系数是 0（蒸不额外加油），
        # 而「每日用油总量」是按烹饪方式折算的——真在配方里放油，日志里的油会凭空少一截，
        # 那笔差额会被第二层校准当成「实际比推算多用油」，是凭空造出来的冲突。
        [("sugar", "3.000")],
        is_breakfast_staple=True,
    ),
    _DishRow(
        "boiled_egg",
        "煮鸡蛋",
        DishCategory.HALF_MEAT,
        CookingMethod.BOIL,
        "55.00",
        "200.00",
        ["蛋"],
        [("egg", "55.000", None)],
        [],
        is_breakfast_staple=True,
    ),
    _DishRow(
        "egg_pancake",
        "鸡蛋饼",
        DishCategory.HALF_MEAT,
        CookingMethod.STIR_FRY,
        "100.00",
        "40.00",
        ["小麦", "蛋"],
        [("flour", "45.000", None), ("egg", "30.000", None)],
        [("soybean_oil", "4.000"), ("salt", "0.500")],
        is_breakfast_staple=True,
    ),
    _DishRow(
        "hot_milk",
        "热牛奶",
        DishCategory.DRINK,
        CookingMethod.BOIL,
        "250.00",
        "100.00",
        ["奶"],
        [("milk", "250.000", None)],
        [],
        is_breakfast_staple=True,
    ),
    _DishRow(
        "breakfast_tomato_egg",
        "晨光番茄蛋",
        DishCategory.HALF_MEAT,
        CookingMethod.STIR_FRY,
        "140.00",
        "40.00",
        ["蛋"],
        [("tomato", "70.000", None), ("egg", "50.000", None)],
        [("soybean_oil", "4.000"), ("salt", "0.800")],
        is_breakfast_staple=True,
    ),
    _DishRow(
        "breakfast_bok_choy",
        "清炒小油菜",
        DishCategory.VEGETABLE,
        CookingMethod.STIR_FRY,
        "120.00",
        "40.00",
        [],
        [("bok_choy", "110.000", None), ("garlic", "5.000", None)],
        [("soybean_oil", "4.000"), ("salt", "0.800")],
        is_breakfast_staple=True,
    ),
    _DishRow(
        "breakfast_tofu_soup",
        "豆腐蛋花汤",
        DishCategory.SOUP,
        CookingMethod.BOIL,
        "220.00",
        "60.00",
        ["蛋", "大豆"],
        [("tofu", "40.000", None), ("egg", "10.000", None)],
        [("salt", "0.600"), ("soybean_oil", "0.500")],
        is_breakfast_staple=True,
    ),
    _DishRow(
        "breakfast_carrot_pancake",
        "胡萝卜鸡蛋饼",
        DishCategory.HALF_MEAT,
        CookingMethod.STIR_FRY,
        "100.00",
        "40.00",
        ["小麦", "蛋"],
        [
            ("flour", "35.000", None),
            ("egg", "25.000", None),
            ("carrot", "20.000", None),
        ],
        [("soybean_oil", "3.000"), ("salt", "0.400")],
        is_breakfast_staple=True,
    ),
    _DishRow(
        "breakfast_cabbage",
        "醋香白菜",
        DishCategory.VEGETABLE,
        CookingMethod.STIR_FRY,
        "120.00",
        "40.00",
        [],
        [("cabbage", "100.000", None)],
        [
            ("soybean_oil", "4.000"),
            ("salt", "0.800"),
            ("vinegar", "3.000"),
        ],
        is_breakfast_staple=True,
    ),
]


def seed_dishes(
    session: Session,
    tally: _Tally,
    ingredient_ids: dict[str, UUID],
    seasoning_ids: dict[str, UUID],
) -> dict[str, UUID]:
    dish_ids: dict[str, UUID] = {}
    for row in _DISHES:
        dish_id = _stable_id("dish", row.key)
        dish_ids[row.key] = dish_id
        tally.add(
            "菜品",
            _upsert(
                session,
                Dish,
                dish_id,
                name=row.name,
                category=row.category,
                cooking_method=row.cooking_method,
                standard_serving_g=Decimal(row.standard_serving_g),
                servings_per_pot=Decimal(row.servings_per_pot),
                allergens=row.allergens,
                is_breakfast_staple=row.is_breakfast_staple,
                recipe_version=1,
                is_active=True,
            ),
        )

        for ingredient_key, quantity, ratio_override in row.items:
            tally.add(
                "配方食材",
                # 按 (菜品, 食材) 这个自然键写入，而不是按确定性主键：
                # 配方可能在界面上被改过，那时行主键已经换了，只有自然键还靠得住
                _upsert_by(
                    session,
                    RecipeItem,
                    {"dish_id": dish_id, "ingredient_id": ingredient_ids[ingredient_key]},
                    quantity_per_serving_g=Decimal(quantity),
                    edible_ratio_override=(
                        Decimal(ratio_override) if ratio_override is not None else None
                    ),
                ),
            )

        for seasoning_key, quantity in row.seasonings:
            tally.add(
                "配方调味料",
                _upsert_by(
                    session,
                    RecipeSeasoning,
                    {"dish_id": dish_id, "seasoning_id": seasoning_ids[seasoning_key]},
                    quantity_per_serving_g=Decimal(quantity),
                ),
            )

    session.flush()
    return dish_ids


# ---------------------------------------------------------------------------
# 膳食指南基准
# ---------------------------------------------------------------------------
_STANDARDS: list[dict[str, Any]] = [
    {
        "code": StandardCode.SALT,
        "name": "食盐",
        "unit": "g",
        "nutrient": None,
        "target_min": None,
        "target_max": Decimal("5.000"),
        "source_quote": "每天摄入食盐不超过5克",
    },
    {
        "code": StandardCode.EDIBLE_OIL,
        "name": "烹调油",
        "unit": "g",
        "nutrient": None,
        "target_min": Decimal("25.000"),
        "target_max": Decimal("30.000"),
        "source_quote": "每天烹调油25~30克",
    },
    {
        "code": StandardCode.ADDED_SUGAR,
        "name": "添加糖",
        "unit": "g",
        "nutrient": None,
        "target_min": None,
        "target_max": Decimal("50.000"),
        "source_quote": "每天添加糖摄入量不超过50克，最好控制在25克以下",
    },
    {
        "code": StandardCode.FOOD_VARIETY,
        "name": "食物种类数",
        "unit": "种",
        "nutrient": None,
        "target_min": Decimal("12.000"),
        "target_max": None,
        "source_quote": "平均每天摄入12种以上食物，每周25种以上",
    },
]

_STANDARD_SOURCE = "《中国居民膳食指南（2022）》"
_STANDARD_SOURCE_VERSION = "2022"


def seed_nutrition_standards(session: Session, tally: _Tally) -> None:
    """写入《中国居民膳食指南（2022）》里可量化的群体基准。

    刻意**不**写入能量与三大营养素的供给量：指南给出的是按年龄段、性别的区间与
    供能比，需要《学生餐营养指南》的原文才能确定本系统的目标值。需求文档的
    「待确认事项 1」记的就是这个空白，这里保持空缺而不是编一个数字填上。
    """
    for row in _STANDARDS:
        tally.add(
            "膳食基准",
            _upsert(
                session,
                NutritionStandard,
                _stable_id("standard", row["code"]),
                code=row["code"],
                name=row["name"],
                unit=row["unit"],
                nutrient=row["nutrient"],
                period=StandardPeriod.DAILY,
                target_min=row["target_min"],
                target_max=row["target_max"],
                source=_STANDARD_SOURCE,
                source_version=_STANDARD_SOURCE_VERSION,
                source_quote=row["source_quote"],
                is_active=True,
            ),
        )
    session.flush()


#: 节假日当天的在校人数折减，与 `forecast.strategy.HOLIDAY_FACTOR` 同口径：
#: 历史数据与预测用的日历必须是一套，否则回测测的是两者的差，不是模型的准头。
#: 日历本身由迁移写入（参考数据，任何环境都该有），这里只按它折减历史份数。
_HOLIDAY_DINER_FACTOR = 0.45

# ---------------------------------------------------------------------------
# 两周历史数据
# ---------------------------------------------------------------------------
# 每餐的供应结构：一道主食、一道汤、一道荤菜、一道半荤、一道素菜。
# 每天从每个池子里各取一道，轮换周期拉得足够长，菜单看起来才不会重复。
_STAPLES: tuple[str, ...] = ("steamed_rice", "steamed_bun")
_SOUPS: tuple[str, ...] = (
    "nori_egg_soup",
    "tomato_egg_soup",
    "winter_melon_rib_soup",
    "winter_melon_egg_soup",
    "tomato_tofu_soup",
    "nori_tofu_soup",
)
_MEATS: tuple[str, ...] = (
    "beef_potato",
    "braised_pork",
    "chicken_potato",
    "steamed_bass",
    "kungpao_chicken",
    "tomato_beef",
)
_HALF_MEATS: tuple[str, ...] = (
    "tomato_egg",
    "wood_ear_pork",
    "mapo_tofu",
    "pepper_pork",
    "carrot_egg",
    "chicken_cucumber",
    "prawn_tofu",
)
_VEGETABLES: tuple[str, ...] = (
    "stir_broccoli",
    "garlic_bok_choy",
    "vinegar_cabbage",
    "cucumber_salad",
    "dry_fried_beans",
    "garlic_broccoli",
    "pepper_potato",
    "onion_wood_ear",
    "carrot_stir",
)

#: (菜品池, 步长, 起始偏移)。步长与池长互质，取值才不会总落在同一个位置；
#: 各池给不同的偏移，避免几道菜永远同时出现。
#: 轮换基准日：锚在固定日期上，同一天永远供应同一批菜，历史不会随日子往前跑而改写。
_ROTATION_EPOCH = date(2026, 1, 1)

#: 各餐次的轮换。晚餐把每个池的起始偏移整体往前挪一位，于是同一天的晚餐与午餐
#: 在**每一个类别里都取到不同的菜**——这与推荐里「同一天另一餐排过的不再选
#: （主食除外）」是同一件事。历史与规则对不上的话，回测测出来的是两者的差，
#: 不是模型的准头，而这种自相矛盾最难查。
_ROTATION_BY_MEAL: dict[MealType, tuple[tuple[tuple[str, ...], int, int], ...]] = {
    MealType.LUNCH: (
        (_STAPLES, 3, 0),
        (_SOUPS, 5, 0),
        (_MEATS, 1, 0),
        (_HALF_MEATS, 2, 1),
        (_VEGETABLES, 4, 2),
    ),
    MealType.DINNER: (
        (_STAPLES, 3, 1),
        (_SOUPS, 5, 1),
        (_MEATS, 1, 1),
        (_HALF_MEATS, 2, 2),
        (_VEGETABLES, 5, 3),
    ),
}

#: 早餐每天固定供应这几道。必须与菜品库里勾了「早餐固定供应」的那几道一致：
#: 种子写的是历史、标记决定推荐，两边不一致就会出现「历史里早餐有牛奶、
#: 大屏上却没有」这种对不上的状态。
_BREAKFAST_MENU: tuple[str, ...] = (
    "congee",
    "steamed_roll",
    "boiled_egg",
    "egg_pancake",
    "hot_milk",
    "breakfast_tomato_egg",
    "breakfast_bok_choy",
    "breakfast_tofu_soup",
    "breakfast_carrot_pancake",
    "breakfast_cabbage",
)

#: 各餐次就餐人次相对午餐的系数。早餐人少、晚餐略少于午餐：这既是食堂的实情，
#: 也让「按同星期历史预测份数」在三个餐次上各自有信号可抓。
_DINER_FACTOR_BY_MEAL: dict[MealType, float] = {
    MealType.BREAKFAST: 0.55,
    MealType.LUNCH: 1.0,
    MealType.DINNER: 0.85,
}

#: 各餐次记在菜单日上的轮换名
_ROTATION_NAME_BY_MEAL: dict[MealType, str] = {
    MealType.BREAKFAST: "早餐固定",
    MealType.LUNCH: "演示两周轮换",
    MealType.DINNER: "演示两周轮换",
}

#: 各餐次的提交时间，只是让演示数据看起来像人录的
_SUBMIT_TIME_BY_MEAL: dict[MealType, time] = {
    MealType.BREAKFAST: time(8, 30),
    MealType.LUNCH: time(13, 30),
    MealType.DINNER: time(19, 30),
}

# 各菜品的受欢迎程度（出餐份数占当餐就餐人次的比例），用于生成有起伏但合理的份数序列
_POPULARITY: dict[str, float] = {
    "steamed_rice": 0.90,
    "steamed_bun": 0.25,
    "nori_egg_soup": 0.55,
    "tomato_egg_soup": 0.50,
    "winter_melon_rib_soup": 0.48,
    "beef_potato": 0.51,
    "braised_pork": 0.46,
    "chicken_potato": 0.49,
    "steamed_bass": 0.35,
    "kungpao_chicken": 0.47,
    "tomato_egg": 0.62,
    "wood_ear_pork": 0.45,
    "mapo_tofu": 0.50,
    "pepper_pork": 0.44,
    "carrot_egg": 0.40,
    "stir_broccoli": 0.44,
    "garlic_bok_choy": 0.42,
    "vinegar_cabbage": 0.38,
    "cucumber_salad": 0.36,
    "dry_fried_beans": 0.41,
    "winter_melon_egg_soup": 0.48,
    "tomato_tofu_soup": 0.46,
    "nori_tofu_soup": 0.45,
    "garlic_broccoli": 0.43,
    "pepper_potato": 0.40,
    "onion_wood_ear": 0.37,
    "carrot_stir": 0.39,
    "tomato_beef": 0.48,
    "chicken_cucumber": 0.43,
    "prawn_tofu": 0.39,
    # 早餐：比例是「出餐份数 ÷ 早餐就餐人次」
    "congee": 0.78,
    "steamed_roll": 0.46,
    "boiled_egg": 0.81,
    "egg_pancake": 0.34,
    "hot_milk": 0.52,
    "breakfast_tomato_egg": 0.45,
    "breakfast_bok_choy": 0.32,
    "breakfast_tofu_soup": 0.38,
    "breakfast_carrot_pancake": 0.30,
    "breakfast_cabbage": 0.28,
}

#: 周末在校人数明显低于工作日。不去人为制造这个差异的话，
#: 「同星期移动平均」这个预测模型就没有任何真实信号可以捕捉。
_WEEKEND_DINER_FACTOR = 0.45

# 大锅菜实际用油与配方推算值之间的系统性偏差，按烹饪方式分组——
# 这正是第三层之外「第二层 当日闭环校准」要修正的对象，预置进来后续模块才有东西可算
_OIL_BIAS_BY_METHOD: dict[CookingMethod, float] = {
    CookingMethod.STIR_FRY: 1.18,
    CookingMethod.STEW: 1.06,
    CookingMethod.BOIL: 0.95,
    CookingMethod.STEAM: 0.0,
    CookingMethod.DEEP_FRY: 1.35,
    CookingMethod.COLD_DRESS: 1.0,
}

_SALT_BIAS = 1.09
_SUGAR_BIAS = 1.02


def _served_dishes(day_index: int, meal_type: MealType) -> list[str]:
    """这一天这一餐供应哪几道菜。

    早餐是固定组合，午晚餐按各自那条轮换取——两条轮换的起始偏移错开一位，
    所以同一天的晚餐与午餐在每个类别里都是不同的菜。
    """
    if meal_type is MealType.BREAKFAST:
        return list(_BREAKFAST_MENU)
    return [
        pool[(day_index * step + start) % len(pool)]
        for pool, step, start in _ROTATION_BY_MEAL[meal_type]
    ]


def seed_history(
    session: Session,
    tally: _Tally,
    dish_ids: dict[str, UUID],
    ingredient_ids: dict[str, UUID],
    seasoning_ids: dict[str, UUID],
    recorder_id: UUID,
    days: int = HISTORY_DAYS,
) -> None:
    """生成最近 N 天（含今天）**早中晚三餐**的菜单与每日记录。

    用固定种子的伪随机数，保证每次执行生成完全相同的数值——否则「重跑不产生变化」
    这条幂等性质就不成立了。
    """
    settings = get_settings()
    rng = random.Random(20261014)
    today = datetime.now(settings.timezone).date()
    window_start = today - timedelta(days=days - 1)
    # 收敛窗口：早于这次的演示行要清掉。窗口是「截至今天的 N 天」，随今天往前挪，
    # 不清的话库里会一天多留一天——过几天演示历史就变成 60 多天，
    # 「种子历史恰好 8 周」不再成立，也没人说得清多出来那天算不算数。
    session.execute(delete(MenuDay).where(MenuDay.date < window_start))
    session.execute(delete(DailyLog).where(DailyLog.date < window_start))
    session.execute(delete(DishNutrition).where(DishNutrition.date < window_start))
    session.flush()
    # 日历从库里读，种子不再自己抄一份：两处各写一份迟早会对不上，
    # 而一旦对不上，回测测出来的是两者的差，不是模型的准头。
    calendar = {row.date: row.kind for row in session.scalars(select(Holiday)).all()}
    dish_lookup = {row.key: row for row in _DISHES}
    seasoning_category_lookup = {row.key: row.category.value for row in _SEASONINGS}

    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        # 轮换的「第几天」锚在日历日期上，而不是「窗口内第几天」。
        # 用窗口内序号的话，每过一天整个窗口前移，同一天供应的菜就全变了——
        # 演示历史每天都在改写，看板与回测的数字跟着漂，谁也说不清哪个是真的。
        day_index = (day - _ROTATION_EPOCH).days

        # 节假日当天的在校人数确实会掉下来。种子里必须体现这一点，
        # 否则「历史按普通日子生成、预测却按节假日折减」，回测会平白多出一大截误差——
        # 那不是模型的错，是演示数据自相矛盾。
        kind = calendar.get(day)
        holiday_factor = _HOLIDAY_DINER_FACTOR if kind is HolidayKind.HOLIDAY else 1.0
        # 调休上班的周末要按工作日算：那天是要上班的，不能套周末的折减
        is_weekend = day.weekday() >= 5 and kind is not HolidayKind.WORKDAY
        weekday_factor = _WEEKEND_DINER_FACTOR if is_weekend else 1.0
        # 午餐的人次是基准，另外两餐按系数折算（见 _DINER_FACTOR_BY_MEAL）
        lunch_diners = max(
            1, round((950 + rng.randrange(-120, 121)) * weekday_factor * holiday_factor)
        )

        for meal_type in (MealType.BREAKFAST, MealType.LUNCH, MealType.DINNER):
            served = _served_dishes(day_index, meal_type)
            diner_count = max(1, round(lunch_diners * _DINER_FACTOR_BY_MEAL[meal_type]))

            # 按自然键认领已有行，而不是硬插一个固定主键：这一天可能已经被别的东西写过
            # （例如端到端用例在昨天往「明天」录了一餐，而昨天的那天就是今天）。
            # 数据库有 (date, meal_type) 唯一约束，硬插会直接撞上；认领则把它收敛到种子定义。
            menu_day_id = _existing_id(
                session, MenuDay, {"date": day, "meal_type": meal_type}
            ) or _stable_id("menu_day", f"{day.isoformat()}:{meal_type.value}")
            tally.add(
                "菜单日",
                _upsert(
                    session,
                    MenuDay,
                    menu_day_id,
                    date=day,
                    meal_type=meal_type,
                    rotation_name=_ROTATION_NAME_BY_MEAL[meal_type],
                    created_by=recorder_id,
                ),
            )

            daily_log_id = _existing_id(
                session, DailyLog, {"date": day, "meal_type": meal_type}
            ) or _stable_id("daily_log", f"{day.isoformat()}:{meal_type.value}")

            # 清掉这一天这一餐不在当前计划内的旧明细。种子脚本要能把演示库**收敛**到当前
            # 定义，而不是每改一次菜单就多留一批孤儿行——那些行会悄悄混进人均摄入的
            # 聚合里，让看板上的数字变得无法解释。
            #
            # 营养结果那一条必须带上餐次：它是按 (日期, 餐次, 菜品) 存的，只按日期+菜品删
            # 会把另外两餐的结果一起删掉，而它们随即要被重算——看起来没事，直到某天
            # 重算没跟上，大屏就少了一餐。
            served_ids = [dish_ids[key] for key in served]
            session.execute(
                delete(MenuDayItem).where(
                    MenuDayItem.menu_day_id == menu_day_id,
                    MenuDayItem.dish_id.not_in(served_ids),
                )
            )
            session.execute(
                delete(DailyLogItem).where(
                    DailyLogItem.daily_log_id == daily_log_id,
                    DailyLogItem.dish_id.not_in(served_ids),
                )
            )
            session.execute(
                delete(DishNutrition).where(
                    DishNutrition.date == day,
                    DishNutrition.meal_type == meal_type,
                    DishNutrition.dish_id.not_in(served_ids),
                )
            )

            oil_total = Decimal("0")
            salt_total = Decimal("0")
            sugar_total = Decimal("0")
            leftover_total = Decimal("0")
            item_rows: list[tuple[str, Decimal, Decimal]] = []

            for dish_key in served:
                row = dish_lookup[dish_key]
                servings = Decimal(str(round(diner_count * _POPULARITY[dish_key])))
                leftover_ratio = Decimal(str(round(rng.uniform(0.02, 0.14), 4)))

                tally.add(
                    "菜单日菜品",
                    _upsert(
                        session,
                        MenuDayItem,
                        _existing_id(
                            session,
                            MenuDayItem,
                            {"menu_day_id": menu_day_id, "dish_id": dish_ids[dish_key]},
                        )
                        or _stable_id(
                            "menu_day_item", f"{day.isoformat()}:{meal_type.value}:{dish_key}"
                        ),
                        menu_day_id=menu_day_id,
                        dish_id=dish_ids[dish_key],
                        planned_servings=servings,
                        is_substituted=False,
                    ),
                )

                item_rows.append((dish_key, servings, leftover_ratio))

                for seasoning_key, quantity in row.seasonings:
                    amount = Decimal(quantity) * servings
                    if seasoning_key == "soybean_oil":
                        oil_total += amount * Decimal(str(_OIL_BIAS_BY_METHOD[row.cooking_method]))
                    elif seasoning_key == "salt":
                        salt_total += amount * Decimal(str(_SALT_BIAS))
                    elif seasoning_key == "sugar":
                        sugar_total += amount * Decimal(str(_SUGAR_BIAS))

                leftover_total += servings * leftover_ratio * Decimal(row.standard_serving_g)

            tally.add(
                "每日记录",
                _upsert(
                    session,
                    DailyLog,
                    daily_log_id,
                    date=day,
                    meal_type=meal_type,
                    diner_count=diner_count,
                    oil_total_g=oil_total.quantize(Decimal("0.01")),
                    salt_total_g=salt_total.quantize(Decimal("0.01")),
                    sugar_total_g=sugar_total.quantize(Decimal("0.01")),
                    leftover_weight_g=leftover_total.quantize(Decimal("0.01")),
                    anomaly_flags=[],
                    submitted_by=recorder_id,
                    submitted_at=datetime.combine(
                        day, _SUBMIT_TIME_BY_MEAL[meal_type], tzinfo=settings.timezone
                    ),
                ),
            )

            for dish_key, servings, leftover_ratio in item_rows:
                row = dish_lookup[dish_key]
                tally.add(
                    "每日明细",
                    _upsert(
                        session,
                        DailyLogItem,
                        _existing_id(
                            session,
                            DailyLogItem,
                            {"daily_log_id": daily_log_id, "dish_id": dish_ids[dish_key]},
                        )
                        or _stable_id(
                            "daily_log_item", f"{day.isoformat()}:{meal_type.value}:{dish_key}"
                        ),
                        daily_log_id=daily_log_id,
                        dish_id=dish_ids[dish_key],
                        servings_produced=servings,
                        recipe_snapshot={
                            "recipe_version": 1,
                            "cooking_method": row.cooking_method.value,
                            "ingredients": [
                                {
                                    "ingredient_id": str(ingredient_ids[ingredient_key]),
                                    "quantity_per_serving_g": quantity,
                                    "edible_ratio_override": edible_override,
                                }
                                for ingredient_key, quantity, edible_override in row.items
                            ],
                            "seasonings": [
                                {
                                    "seasoning_id": str(seasoning_ids[seasoning_key]),
                                    "category": seasoning_category_lookup[seasoning_key],
                                    "quantity_per_serving_g": quantity,
                                }
                                for seasoning_key, quantity in row.seasonings
                            ],
                        },
                        leftover_ratio=leftover_ratio,
                        leftover_weight_g=(
                            servings * leftover_ratio * Decimal(row.standard_serving_g)
                        ).quantize(Decimal("0.01")),
                    ),
                )

    session.flush()


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def run(session: Session, *, history_days: int = HISTORY_DAYS) -> _Tally:
    """执行全部种子步骤。返回统计结果供调用方断言。"""
    tally = _Tally()
    user_ids = seed_users(session, tally)
    ingredient_ids = seed_ingredients(session, tally)
    seasoning_ids = seed_seasonings(session, tally)
    dish_ids = seed_dishes(session, tally, ingredient_ids, seasoning_ids)
    seed_nutrition_standards(session, tally)
    seed_history(
        session,
        tally,
        dish_ids,
        ingredient_ids,
        seasoning_ids,
        user_ids["recorder"],
        days=history_days,
    )
    session.commit()
    return tally


def main() -> int:
    configure_logging("INFO")
    settings = get_settings()
    # 种子脚本会写入带已知口令的演示账号，生产环境默认拒绝执行。
    # 内网首次部署确实需要初始化演示数据时，显式设置 ALLOW_DEMO_SEED=true 放行。
    if settings.is_production and os.environ.get("ALLOW_DEMO_SEED", "").lower() not in {
        "1",
        "true",
        "yes",
    }:
        logger.error(
            "生产环境默认拒绝执行种子脚本（它会写入带已知口令的演示账号）。"
            "确需初始化演示数据，请显式设置 ALLOW_DEMO_SEED=true"
        )
        return 1

    with get_session_factory()() as session:
        tally = run(session)

    logger.info("种子数据执行完成：\n%s", tally.report())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

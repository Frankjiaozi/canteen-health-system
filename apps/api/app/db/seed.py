"""种子数据脚本。

用法：

    pnpm db:seed

## 幂等设计

所有实体都以「自然键 → 确定性 UUID」（uuid5）作为主键，并逐字段比对后才决定是否写库。
因此脚本可以随时重跑：第二次执行不会新增任何行，也不会产生无意义的 UPDATE。

## 关于内置营养数值

脚本里的食材成分是**演示占位值**，不是权威数据。正式参赛前必须逐条与
《中国食物成分表（标准版第 6 版）》核对，并把 `data_source` 改成真实来源——
系统要求任何营养数据都能点开看到来源与版本，这条要求在演示阶段就必须成立，
因此这里宁可如实标注「待核对」，也不填写一个看起来权威却没有依据的出处。
"""

from __future__ import annotations

import os
import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal
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
# 食材库
# ---------------------------------------------------------------------------
class _IngredientRow(NamedTuple):
    key: str
    name: str
    category: IngredientCategory
    energy_kcal: str
    protein_g: str
    fat_g: str
    carb_g: str
    sodium_mg: str
    edible_ratio: str
    unit_price: str


# 每 100 克可食部的营养值
_INGREDIENTS: list[_IngredientRow] = [
    _IngredientRow(
        "rice",
        "大米",
        IngredientCategory.GRAIN,
        "346.0",
        "7.4",
        "0.8",
        "77.9",
        "3.8",
        "1.0000",
        "5.60",
    ),
    _IngredientRow(
        "flour",
        "小麦粉",
        IngredientCategory.GRAIN,
        "354.0",
        "11.2",
        "1.5",
        "73.6",
        "3.1",
        "1.0000",
        "4.20",
    ),
    _IngredientRow(
        "potato",
        "马铃薯",
        IngredientCategory.GRAIN,
        "81.0",
        "2.6",
        "0.2",
        "17.8",
        "2.7",
        "0.9400",
        "3.00",
    ),
    _IngredientRow(
        "cabbage",
        "大白菜",
        IngredientCategory.VEGETABLE,
        "17.0",
        "1.5",
        "0.1",
        "3.2",
        "57.5",
        "0.8900",
        "1.60",
    ),
    _IngredientRow(
        "broccoli",
        "西兰花",
        IngredientCategory.VEGETABLE,
        "36.0",
        "4.1",
        "0.6",
        "4.3",
        "18.8",
        "0.8300",
        "6.00",
    ),
    _IngredientRow(
        "tomato",
        "番茄",
        IngredientCategory.VEGETABLE,
        "20.0",
        "0.9",
        "0.2",
        "4.0",
        "5.0",
        "1.0000",
        "4.50",
    ),
    _IngredientRow(
        "cucumber",
        "黄瓜",
        IngredientCategory.VEGETABLE,
        "16.0",
        "0.8",
        "0.2",
        "2.9",
        "4.9",
        "0.9200",
        "3.60",
    ),
    _IngredientRow(
        "carrot",
        "胡萝卜",
        IngredientCategory.VEGETABLE,
        "39.0",
        "1.0",
        "0.2",
        "8.8",
        "71.4",
        "0.9600",
        "3.20",
    ),
    _IngredientRow(
        "green_pepper",
        "青椒",
        IngredientCategory.VEGETABLE,
        "22.0",
        "1.4",
        "0.3",
        "5.4",
        "3.3",
        "0.9600",
        "5.00",
    ),
    _IngredientRow(
        "onion",
        "洋葱",
        IngredientCategory.VEGETABLE,
        "40.0",
        "1.1",
        "0.2",
        "9.0",
        "4.4",
        "0.8800",
        "3.40",
    ),
    _IngredientRow(
        "bok_choy",
        "油菜",
        IngredientCategory.VEGETABLE,
        "25.0",
        "1.8",
        "0.5",
        "3.8",
        "55.8",
        "0.8700",
        "3.80",
    ),
    _IngredientRow(
        "wood_ear",
        "木耳（干）",
        IngredientCategory.FUNGUS_ALGAE,
        "265.0",
        "12.1",
        "1.5",
        "65.6",
        "48.5",
        "1.0000",
        "32.00",
    ),
    _IngredientRow(
        "nori",
        "紫菜（干）",
        IngredientCategory.FUNGUS_ALGAE,
        "250.0",
        "26.7",
        "1.1",
        "44.1",
        "710.3",
        "1.0000",
        "40.00",
    ),
    _IngredientRow(
        "egg",
        "鸡蛋",
        IngredientCategory.EGG,
        "144.0",
        "13.3",
        "8.8",
        "2.8",
        "131.5",
        "0.8500",
        "9.60",
    ),
    _IngredientRow(
        "pork_lean",
        "猪肉（瘦）",
        IngredientCategory.LIVESTOCK_POULTRY,
        "143.0",
        "20.3",
        "6.2",
        "1.5",
        "57.5",
        "1.0000",
        "26.00",
    ),
    _IngredientRow(
        "chicken_breast",
        "鸡胸肉",
        IngredientCategory.LIVESTOCK_POULTRY,
        "133.0",
        "19.4",
        "5.0",
        "2.5",
        "34.4",
        "1.0000",
        "18.00",
    ),
    _IngredientRow(
        "beef_lean",
        "牛肉（瘦）",
        IngredientCategory.LIVESTOCK_POULTRY,
        "106.0",
        "20.2",
        "2.3",
        "1.2",
        "53.6",
        "1.0000",
        "62.00",
    ),
    _IngredientRow(
        "prawn",
        "对虾",
        IngredientCategory.AQUATIC,
        "93.0",
        "18.6",
        "0.8",
        "2.8",
        "165.2",
        "0.6100",
        "45.00",
    ),
    _IngredientRow(
        "tofu",
        "豆腐（北）",
        IngredientCategory.BEAN,
        "116.0",
        "12.2",
        "4.8",
        "4.2",
        "7.2",
        "1.0000",
        "5.20",
    ),
    _IngredientRow(
        "apple",
        "苹果",
        IngredientCategory.FRUIT,
        "53.0",
        "0.2",
        "0.2",
        "13.5",
        "1.6",
        "0.7600",
        "7.00",
    ),
    _IngredientRow(
        "milk",
        "牛奶",
        IngredientCategory.DAIRY,
        "54.0",
        "3.0",
        "3.2",
        "3.4",
        "37.2",
        "1.0000",
        "8.00",
    ),
    _IngredientRow(
        "sesame_oil",
        "芝麻油",
        IngredientCategory.OIL_FAT,
        "898.0",
        "0.0",
        "99.7",
        "0.2",
        "1.1",
        "1.0000",
        "26.00",
    ),
    _IngredientRow(
        "pork_belly",
        "猪肉（五花）",
        IngredientCategory.LIVESTOCK_POULTRY,
        "508.0",
        "7.7",
        "53.0",
        "2.4",
        "37.5",
        "1.0000",
        "24.00",
    ),
    _IngredientRow(
        "chicken_leg",
        "鸡腿肉",
        IngredientCategory.LIVESTOCK_POULTRY,
        "181.0",
        "16.0",
        "13.0",
        "0.0",
        "64.0",
        "0.6900",
        "16.00",
    ),
    _IngredientRow(
        "pork_rib",
        "猪大排",
        IngredientCategory.LIVESTOCK_POULTRY,
        "264.0",
        "18.3",
        "20.4",
        "1.7",
        "44.5",
        "0.7500",
        "38.00",
    ),
    _IngredientRow(
        "sea_bass",
        "鲈鱼",
        IngredientCategory.AQUATIC,
        "105.0",
        "18.6",
        "3.4",
        "0.0",
        "144.1",
        "0.5800",
        "32.00",
    ),
    _IngredientRow(
        "peanut",
        "花生仁（炒）",
        IngredientCategory.NUT,
        "601.0",
        "21.7",
        "48.0",
        "23.8",
        "34.8",
        "1.0000",
        "12.00",
    ),
    _IngredientRow(
        "garlic",
        "大蒜",
        IngredientCategory.VEGETABLE,
        "128.0",
        "4.5",
        "0.2",
        "27.6",
        "19.6",
        "0.8500",
        "9.00",
    ),
    _IngredientRow(
        "green_bean",
        "四季豆",
        IngredientCategory.VEGETABLE,
        "31.0",
        "2.0",
        "0.4",
        "5.7",
        "8.6",
        "0.9600",
        "7.00",
    ),
    _IngredientRow(
        "winter_melon",
        "冬瓜",
        IngredientCategory.VEGETABLE,
        "12.0",
        "0.4",
        "0.2",
        "2.6",
        "1.8",
        "0.8000",
        "3.00",
    ),
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
                energy_kcal=Decimal(row.energy_kcal),
                protein_g=Decimal(row.protein_g),
                fat_g=Decimal(row.fat_g),
                carb_g=Decimal(row.carb_g),
                sodium_mg=Decimal(row.sodium_mg),
                edible_ratio=Decimal(row.edible_ratio),
                unit_price=Decimal(row.unit_price),
                data_source=DEMO_DATA_SOURCE,
                source_version=DEMO_SOURCE_VERSION,
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
    energy_kcal: str
    protein_g: str
    fat_g: str
    carb_g: str
    sodium_mg: str
    unit_price: str


# 每 100 克计，与食材库同一口径，便于统一计算
_SEASONINGS: list[_SeasoningRow] = [
    _SeasoningRow(
        "soybean_oil",
        "大豆油",
        SeasoningCategory.EDIBLE_OIL,
        "899.0",
        "0.0",
        "99.9",
        "0.0",
        "0.0",
        "12.00",
    ),
    _SeasoningRow(
        "salt", "食盐", SeasoningCategory.SALT, "0.0", "0.0", "0.0", "0.0", "39311.0", "2.50"
    ),
    _SeasoningRow(
        "sugar", "白砂糖", SeasoningCategory.SUGAR, "400.0", "0.0", "0.0", "99.9", "0.4", "6.00"
    ),
    _SeasoningRow(
        "soy_sauce",
        "生抽酱油",
        SeasoningCategory.SOY_SAUCE,
        "63.0",
        "5.6",
        "0.1",
        "10.1",
        "5757.0",
        "8.00",
    ),
    _SeasoningRow(
        "oyster_sauce",
        "蚝油",
        SeasoningCategory.OYSTER_SAUCE,
        "114.0",
        "4.0",
        "0.3",
        "24.0",
        "2000.0",
        "10.00",
    ),
    _SeasoningRow(
        "corn_starch",
        "玉米淀粉",
        SeasoningCategory.STARCH,
        "345.0",
        "1.2",
        "0.1",
        "85.0",
        "5.0",
        "7.00",
    ),
    _SeasoningRow(
        "bean_paste",
        "豆瓣酱",
        SeasoningCategory.OTHER,
        "178.0",
        "13.6",
        "6.8",
        "17.1",
        "6012.0",
        "12.00",
    ),
    _SeasoningRow(
        "vinegar",
        "陈醋",
        SeasoningCategory.OTHER,
        "31.0",
        "2.1",
        "0.3",
        "4.9",
        "262.1",
        "5.00",
    ),
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
                energy_kcal=Decimal(row.energy_kcal),
                protein_g=Decimal(row.protein_g),
                fat_g=Decimal(row.fat_g),
                carb_g=Decimal(row.carb_g),
                sodium_mg=Decimal(row.sodium_mg),
                unit_price=Decimal(row.unit_price),
                data_source=DEMO_DATA_SOURCE,
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


# ---------------------------------------------------------------------------
# 法定节假日日历
# ---------------------------------------------------------------------------
#: 2026 年七个法定节日的**公历日期**。农历节日的公历日期由历法决定，可以确定；
#: 但**放假区间与调休上班日由国务院办公厅通知决定**，我没有可靠来源，
#: 所以这里只放节日当天，并把每一条都标成「待核对」，界面上给出核对入口。
#: 在那之前：节日当天会被下调，而节前节后的连休与调休周末仍按普通日子算——
#: 这是已知的偏差，不藏着。
_HOLIDAYS_2026 = (
    (date(2026, 1, 1), "元旦"),
    (date(2026, 2, 17), "春节"),
    (date(2026, 4, 5), "清明节"),
    (date(2026, 5, 1), "劳动节"),
    (date(2026, 6, 19), "端午节"),
    (date(2026, 9, 25), "中秋节"),
    (date(2026, 10, 1), "国庆节"),
)

_HOLIDAY_SOURCE = (
    "待核对：放假区间与调休上班日须以国务院办公厅《关于2026年部分节假日安排的通知》为准"
)

#: 节假日当天的在校人数折减，与 `forecast.strategy.HOLIDAY_FACTOR` 同口径：
#: 历史数据与预测用的日历必须是一套，否则回测测的是两者的差，不是模型的准头。
_HOLIDAY_DINER_FACTOR: dict[date, float] = {day: 0.45 for day, _ in _HOLIDAYS_2026}


def seed_holidays(session: Session, tally: _Tally) -> None:
    """内置一份日历，逐条标注「待核对」。"""
    for day, name in _HOLIDAYS_2026:
        tally.add(
            "节假日",
            _upsert(
                session,
                Holiday,
                _stable_id("holiday", day.isoformat()),
                date=day,
                name=name,
                kind=HolidayKind.HOLIDAY,
                is_verified=False,
                source_note=_HOLIDAY_SOURCE,
            ),
        )
    session.flush()


# ---------------------------------------------------------------------------
# 两周历史数据
# ---------------------------------------------------------------------------
# 每餐的供应结构：一道主食、一道汤、一道荤菜、一道半荤、一道素菜。
# 每天从每个池子里各取一道，轮换周期拉得足够长，菜单看起来才不会重复。
_STAPLES: tuple[str, ...] = ("steamed_rice", "steamed_bun")
_SOUPS: tuple[str, ...] = ("nori_egg_soup", "tomato_egg_soup", "winter_melon_rib_soup")
_MEATS: tuple[str, ...] = (
    "beef_potato",
    "braised_pork",
    "chicken_potato",
    "steamed_bass",
    "kungpao_chicken",
)
_HALF_MEATS: tuple[str, ...] = (
    "tomato_egg",
    "wood_ear_pork",
    "mapo_tofu",
    "pepper_pork",
    "carrot_egg",
)
_VEGETABLES: tuple[str, ...] = (
    "stir_broccoli",
    "garlic_bok_choy",
    "vinegar_cabbage",
    "cucumber_salad",
    "dry_fried_beans",
)

#: (菜品池, 步长, 起始偏移)。步长与池长互质，取值才不会总落在同一个位置；
#: 各池给不同的偏移，避免几道菜永远同时出现。
_MENU_ROTATION: tuple[tuple[tuple[str, ...], int, int], ...] = (
    (_STAPLES, 3, 0),
    (_SOUPS, 2, 0),
    (_MEATS, 1, 0),
    (_HALF_MEATS, 2, 1),
    (_VEGETABLES, 3, 2),
)

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


def seed_history(
    session: Session,
    tally: _Tally,
    dish_ids: dict[str, UUID],
    recorder_id: UUID,
    days: int = HISTORY_DAYS,
) -> None:
    """生成最近 N 天（含今天）的午餐菜单与每日记录。

    用固定种子的伪随机数，保证每次执行生成完全相同的数值——否则「重跑不产生变化」
    这条幂等性质就不成立了。
    """
    settings = get_settings()
    rng = random.Random(20261014)
    today = datetime.now(settings.timezone).date()

    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        day_index = days - 1 - offset

        served = [
            pool[(day_index * step + start) % len(pool)] for pool, step, start in _MENU_ROTATION
        ]

        # 节假日当天的在校人数确实会掉下来。种子里必须体现这一点，
        # 否则「历史按普通日子生成、预测却按节假日折减」，回测会平白多出一大截误差——
        # 那不是模型的错，是演示数据自相矛盾。
        holiday_factor = _HOLIDAY_DINER_FACTOR.get(day, 1.0)
        weekday_factor = _WEEKEND_DINER_FACTOR if day.weekday() >= 5 else 1.0
        diner_count = max(
            1, round((950 + rng.randrange(-120, 121)) * weekday_factor * holiday_factor)
        )
        menu_day_id = _stable_id("menu_day", f"{day.isoformat()}:LUNCH")
        tally.add(
            "菜单日",
            _upsert(
                session,
                MenuDay,
                menu_day_id,
                date=day,
                meal_type=MealType.LUNCH,
                rotation_name="演示两周轮换",
                created_by=recorder_id,
            ),
        )

        daily_log_id = _stable_id("daily_log", f"{day.isoformat()}:LUNCH")

        # 清掉这一天不在当前计划内的旧明细。种子脚本要能把演示库**收敛**到当前
        # 定义，而不是每改一次菜单就多留一批孤儿行——那些行会悄悄混进人均摄入的
        # 聚合里，让看板上的数字变得无法解释。
        served_ids = [dish_ids[key] for key in served]
        session.execute(
            delete(MenuDayItem).where(
                MenuDayItem.menu_day_id == menu_day_id, MenuDayItem.dish_id.not_in(served_ids)
            )
        )
        session.execute(
            delete(DailyLogItem).where(
                DailyLogItem.daily_log_id == daily_log_id, DailyLogItem.dish_id.not_in(served_ids)
            )
        )
        session.execute(
            delete(DishNutrition).where(
                DishNutrition.date == day, DishNutrition.dish_id.not_in(served_ids)
            )
        )

        oil_total = Decimal("0")
        salt_total = Decimal("0")
        sugar_total = Decimal("0")
        leftover_total = Decimal("0")
        item_rows: list[tuple[str, Decimal, Decimal]] = []

        dish_lookup = {row.key: row for row in _DISHES}
        for dish_key in served:
            row = dish_lookup[dish_key]
            servings = Decimal(str(round(diner_count * _POPULARITY[dish_key])))
            leftover_ratio = Decimal(str(round(rng.uniform(0.02, 0.14), 4)))

            tally.add(
                "菜单日菜品",
                _upsert(
                    session,
                    MenuDayItem,
                    _stable_id("menu_day_item", f"{day.isoformat()}:{dish_key}"),
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
                meal_type=MealType.LUNCH,
                diner_count=diner_count,
                oil_total_g=oil_total.quantize(Decimal("0.01")),
                salt_total_g=salt_total.quantize(Decimal("0.01")),
                sugar_total_g=sugar_total.quantize(Decimal("0.01")),
                leftover_weight_g=leftover_total.quantize(Decimal("0.01")),
                anomaly_flags=[],
                submitted_by=recorder_id,
                submitted_at=datetime.combine(day, time(13, 30), tzinfo=settings.timezone),
            ),
        )

        for dish_key, servings, leftover_ratio in item_rows:
            row = dish_lookup[dish_key]
            tally.add(
                "每日明细",
                _upsert(
                    session,
                    DailyLogItem,
                    _stable_id("daily_log_item", f"{day.isoformat()}:{dish_key}"),
                    daily_log_id=daily_log_id,
                    dish_id=dish_ids[dish_key],
                    servings_produced=servings,
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
    seed_holidays(session, tally)
    seed_history(session, tally, dish_ids, user_ids["recorder"], days=history_days)
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

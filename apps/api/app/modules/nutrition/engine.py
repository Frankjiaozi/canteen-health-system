"""三层校准营养引擎。

本模块是**纯函数 + 不可变 dataclass**：不接触数据库、不读全局配置，调用方负责把 ORM
数据装配成这里的输入结构。这样做有两个好处——算法可以脱离数据库做单元测试
（验收标准里的「5 道菜偏差不超过 15%」能直接写成断言），以及算法实现将来可以整体替换
而不影响业务代码。

这里实现的是三层校准的**第一层：标准配方推算**。第二层（当日闭环校准）与第三层
（抽样纠偏）在后续模块加入，届时只需在本模块追加新的纯函数，由 service 层选择调用。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from app.shared.enums import CookingMethod, SeasoningCategory
from app.shared.nutrients import (
    FIELD_TO_NUTRIENT_CODE,
    NUTRIENT_FIELDS,
    NUTRIENT_SCALES,
)

ENGINE_NAME = "nutrition.theoretical"
ENGINE_VERSION = "1.0.0"
FORMULA = (
    "单份营养 = Σ(食材市品用量 × 可食部比例 ÷ 100 × 每100克成分)"
    " + Σ(调味料用量 ÷ 100 × 每100克成分)"
)

#: 第一层的基准误差。验收标准要求「计算值与称重实测值偏差不超过 15%」，
#: 这里直接把它作为理论值的默认区间半径，而不是给出一个看似精确的点值。
BASE_TOLERANCE = Decimal("0.15")

#: 克重的小数位
GRAM_SCALE = Decimal("0.001")

#: 成分数据缺失时逐步放宽区间：缺失本身就是要如实传达出去的信息
MISSING_DATA_PENALTY = Decimal("0.05")
MAX_MISSING_PENALTY_STEPS = 3

#: 人均口径的额外误差：它除了继承单份的推算误差，还叠加了出餐份数、
#: 剩余比例与就餐人次三项本身就不精确的输入，区间理应比单份更宽。
PER_CAPITA_EXTRA_TOLERANCE = Decimal("0.05")


@dataclass(frozen=True, slots=True)
class NutrientVector:
    """一组营养值。单份与人均都用它表示，靠调用上下文区分口径。"""

    energy_kcal: Decimal
    protein_g: Decimal
    fat_g: Decimal
    carb_g: Decimal
    sodium_mg: Decimal

    def as_dict(self) -> dict[str, Decimal]:
        return {field: getattr(self, field) for field in NUTRIENT_FIELDS}

    def scaled(self, factor: Decimal) -> NutrientVector:
        return NutrientVector(**{field: getattr(self, field) * factor for field in NUTRIENT_FIELDS})

    def rounded(self) -> NutrientVector:
        return NutrientVector(
            **{
                field: getattr(self, field).quantize(
                    Decimal(1).scaleb(-NUTRIENT_SCALES[field]), rounding=ROUND_HALF_UP
                )
                for field in NUTRIENT_FIELDS
            }
        )

    def as_trace(self) -> dict[str, str]:
        return {field: str(getattr(self, field)) for field in NUTRIENT_FIELDS}


@dataclass(frozen=True, slots=True)
class Interval:
    lower: Decimal
    upper: Decimal

    def as_dict(self) -> dict[str, str]:
        return {"lower": str(self.lower), "upper": str(self.upper)}


@dataclass(frozen=True, slots=True)
class IngredientInput:
    """计算所需的食材信息。营养值以每 100 克可食部计，缺失时为 None。"""

    id: UUID
    name: str
    edible_ratio: Decimal
    energy_kcal: Decimal | None
    protein_g: Decimal | None
    fat_g: Decimal | None
    carb_g: Decimal | None
    sodium_mg: Decimal | None
    data_source: str
    source_version: str | None


@dataclass(frozen=True, slots=True)
class RecipeIngredientLine:
    ingredient: IngredientInput
    #: 单份用量，市品重量（克）
    quantity_g: Decimal
    #: 覆盖食材库默认可食部比例，为空则用食材库的值
    edible_ratio_override: Decimal | None = None

    @property
    def edible_ratio(self) -> Decimal:
        if self.edible_ratio_override is not None:
            return self.edible_ratio_override
        return self.ingredient.edible_ratio

    @property
    def edible_quantity_g(self) -> Decimal:
        return self.quantity_g * self.edible_ratio


@dataclass(frozen=True, slots=True)
class SeasoningInput:
    id: UUID
    name: str
    category: SeasoningCategory
    energy_kcal: Decimal | None
    protein_g: Decimal | None
    fat_g: Decimal | None
    carb_g: Decimal | None
    sodium_mg: Decimal | None
    data_source: str | None


@dataclass(frozen=True, slots=True)
class RecipeSeasoningLine:
    seasoning: SeasoningInput
    quantity_g: Decimal


@dataclass(frozen=True, slots=True)
class DishRecipe:
    """一道菜的完整标准配方。"""

    dish_id: UUID
    dish_name: str
    cooking_method: CookingMethod
    recipe_version: int
    ingredients: tuple[RecipeIngredientLine, ...]
    seasonings: tuple[RecipeSeasoningLine, ...]


@dataclass(frozen=True, slots=True)
class NutritionResult:
    """一次计算的全部产出：数值、误差区间与可追溯快照。"""

    per_serving: NutrientVector
    #: 食材部分合计。校准只缩放调味料，因此这一块要单独留出来。
    ingredient_part: NutrientVector
    #: 调味料部分**按类别**合计。油、盐、糖的偏差幅度各不相同，必须分开放。
    seasoning_by_category: dict[SeasoningCategory, NutrientVector]
    uncertainty: dict[str, Interval]
    missing_nutrients: tuple[str, ...]
    trace: dict[str, Any]


class EmptyRecipeError(ValueError):
    """菜品没有任何配方明细，无法参与营养计算。"""


def _contribution(per_100g: Decimal | None, edible_quantity_g: Decimal) -> Decimal:
    """按「每 100 克成分 × 可食部用量」计算单项贡献。

    成分缺失时按 0 计入，同时由调用方记入 `missing_nutrients`——
    把缺失写成 0 却不说明，才是真正会让结论失真的事。
    """
    if per_100g is None:
        return Decimal("0")
    return edible_quantity_g / Decimal("100") * per_100g


def compute_theoretical_per_serving(recipe: DishRecipe) -> NutritionResult:
    """第一层：按标准配方推算单份营养。"""
    if not recipe.ingredients and not recipe.seasonings:
        raise EmptyRecipeError(f"菜品「{recipe.dish_name}」没有配方明细，无法计算营养值")

    totals = dict.fromkeys(NUTRIENT_FIELDS, Decimal("0"))
    missing: set[str] = set()

    ingredient_totals = dict.fromkeys(NUTRIENT_FIELDS, Decimal("0"))
    seasoning_totals: dict[SeasoningCategory, dict[str, Decimal]] = {}

    ingredient_trace: list[dict[str, Any]] = []
    for line in recipe.ingredients:
        ingredient = line.ingredient
        edible_g = line.edible_quantity_g
        for field in NUTRIENT_FIELDS:
            per_100g = getattr(ingredient, field)
            if per_100g is None:
                missing.add(field)
            amount = _contribution(per_100g, edible_g)
            totals[field] += amount
            ingredient_totals[field] += amount
        ingredient_trace.append(
            {
                "name": ingredient.name,
                "quantity_g": str(line.quantity_g),
                "edible_ratio": str(line.edible_ratio),
                # 可食部用量按克保留三位小数：Decimal 相乘会带出多余的零，
                # 而快照是给人看和存档的，不需要 80.0000000 这种噪声
                "edible_quantity_g": str(edible_g.quantize(GRAM_SCALE, rounding=ROUND_HALF_UP)),
                "data_source": ingredient.data_source,
                "source_version": ingredient.source_version,
            }
        )

    seasoning_trace: list[dict[str, Any]] = []
    for seasoning_line in recipe.seasonings:
        seasoning = seasoning_line.seasoning
        # 按调味料类别分开累计：油、盐、糖各有各的校准系数
        bucket = seasoning_totals.setdefault(
            seasoning.category, dict.fromkeys(NUTRIENT_FIELDS, Decimal("0"))
        )
        for field in NUTRIENT_FIELDS:
            per_100g = getattr(seasoning, field)
            if per_100g is None:
                missing.add(field)
            amount = _contribution(per_100g, seasoning_line.quantity_g)
            totals[field] += amount
            bucket[field] += amount
        seasoning_trace.append(
            {
                "name": seasoning.name,
                "quantity_g": str(seasoning_line.quantity_g),
                "data_source": seasoning.data_source,
            }
        )

    per_serving = NutrientVector(**totals).rounded()
    ingredient_part = NutrientVector(**ingredient_totals).rounded()
    seasoning_part = {
        category: NutrientVector(**values).rounded()
        for category, values in seasoning_totals.items()
    }

    missing_codes = tuple(sorted({FIELD_TO_NUTRIENT_CODE[field].value for field in missing}))
    applied_tolerance = tolerance_for(len(missing_codes))
    uncertainty = build_uncertainty(per_serving, missing_nutrients=missing_codes)

    return NutritionResult(
        per_serving=per_serving,
        ingredient_part=ingredient_part,
        seasoning_by_category=seasoning_part,
        uncertainty=uncertainty,
        missing_nutrients=missing_codes,
        trace={
            "engine": ENGINE_NAME,
            "engine_version": ENGINE_VERSION,
            "layer": "标准配方推算",
            "formula": FORMULA,
            "dish_name": recipe.dish_name,
            "cooking_method": recipe.cooking_method.value,
            "recipe_version": recipe.recipe_version,
            "ingredients": ingredient_trace,
            "seasonings": seasoning_trace,
            # 拆开记录食材与调味料各占多少：校准只动调味料那一块，
            # 快照里必须能看出这一刀切在哪里
            "ingredient_part": ingredient_part.as_trace(),
            "seasoning_part": {
                category.value: vector.as_trace() for category, vector in seasoning_part.items()
            },
            "missing_nutrients": list(missing_codes),
            "tolerance": {
                "base": str(BASE_TOLERANCE),
                "applied": str(applied_tolerance),
                "reason": (
                    "配方推算基准误差"
                    if not missing_codes
                    else f"存在 {len(missing_codes)} 项成分数据缺失，已放宽误差区间"
                ),
            },
        },
    )


@dataclass(frozen=True, slots=True)
class CalibrationFactors:
    """要施加到一道菜上的校准系数。

    - `by_category`：第二层当日闭环算出的「按烹饪方式分组、油盐糖各算各的」系数；
    - `overall`：第三层抽样纠偏得到的整体修正比，作用在整块调味料贡献上；
    - `source_note`：写进快照，说清这组系数是怎么来的。
    """

    by_category: dict[SeasoningCategory, Decimal] = dataclass_field(default_factory=dict)
    overall: Decimal = Decimal("1")
    source_note: str = ""


CALIBRATED_TOLERANCE = Decimal("0.10")


def apply_calibration(result: NutritionResult, factors: CalibrationFactors) -> NutrientVector:
    """把校准系数作用到**调味料贡献**上，食材部分原样保留。

    这是「只缩放调味料」这条决定的落点。整道菜乘一个系数看起来更简单，但会把
    「这个食堂连番茄都多放了 10%」这种不存在的偏差算进去，还会把配方本身的录入
    错误一起校准掉、埋起来。
    """
    values: dict[str, Decimal] = {}
    for field_name in NUTRIENT_FIELDS:
        total = getattr(result.ingredient_part, field_name)
        for category, contribution in result.seasoning_by_category.items():
            factor = factors.by_category.get(category, Decimal("1")) * factors.overall
            total += getattr(contribution, field_name) * factor
        values[field_name] = total
    return NutrientVector(**values).rounded()


def calibration_tolerance(*, has_sampling: bool) -> Decimal:
    """校准后适用的相对误差半径。

    有抽样实测撑腰时收紧到 ±10%，只有当日闭环时保持第一层的基准 ±15%——
    闭环修正的是系统性偏差，并不提供「到底准不准」的直接证据。
    """
    return CALIBRATED_TOLERANCE if has_sampling else BASE_TOLERANCE


def compute_theoretical_per_capita(
    per_serving: NutrientVector,
    *,
    servings_produced: Decimal,
    leftover_ratio: Decimal | None,
    diner_count: int,
) -> NutrientVector:
    """第一层：由单份营养推算该菜分摊到每位就餐者的摄入量。

    实际被吃掉的份数 = 出餐份数 × (1 − 剩余比例)，再除以就餐人次。
    当日全部菜品的该口径相加即为当日人均摄入。
    """
    if diner_count <= 0:
        raise ValueError("就餐人次必须大于 0，否则人均摄入没有意义")
    if servings_produced < 0:
        raise ValueError("出餐份数不能为负")

    remaining = Decimal("1") if leftover_ratio is None else Decimal("1") - leftover_ratio
    consumed_servings = servings_produced * remaining
    return per_serving.scaled(consumed_servings / Decimal(diner_count)).rounded()


def tolerance_for(missing_count: int, *, extra: Decimal = Decimal("0")) -> Decimal:
    """当前适用的相对误差半径。"""
    steps = min(missing_count, MAX_MISSING_PENALTY_STEPS)
    return BASE_TOLERANCE + MISSING_DATA_PENALTY * steps + extra


def build_uncertainty(
    nutrients: NutrientVector,
    *,
    missing_nutrients: Sequence[str] = (),
    extra_tolerance: Decimal = Decimal("0"),
) -> dict[str, Interval]:
    """为一组营养值构造逐项误差区间。

    单份与人均各有各的区间：直接拿单份的区间去标注人均值，会出现
    「区间根本没包住数值」这种自相矛盾的展示。
    """
    tolerance = tolerance_for(len(missing_nutrients), extra=extra_tolerance)
    return {field: _interval(getattr(nutrients, field), tolerance) for field in NUTRIENT_FIELDS}


def _interval(value: Decimal, tolerance: Decimal) -> Interval:
    return Interval(
        lower=(value * (Decimal("1") - tolerance)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        ),
        upper=(value * (Decimal("1") + tolerance)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        ),
    )

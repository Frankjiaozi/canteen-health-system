"""营养计算服务：装配输入 → 调用纯函数引擎 → 落库结果。

业务规则集中在这里，引擎保持无状态；两者的边界就是「引擎不碰数据库」。
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import BusinessRuleError, NotFoundError
from app.core.logging import get_logger
from app.modules.nutrition import engine, repository
from app.modules.nutrition.engine import NutrientVector
from app.shared.enums import (
    CalibrationSource,
    CookingMethod,
    MealType,
    NutrientCaliber,
    NutritionValueType,
    SeasoningCategory,
)
from app.shared.standards import quantize

logger = get_logger(__name__)

SOURCE_NOTE_PER_SERVING = "按标准配方推算的单份营养（三层校准第一层）"
SOURCE_NOTE_PER_CAPITA = "按标准配方推算的该菜人均摄入（三层校准第一层）"
SOURCE_NOTE_CALIBRATED = "用当日油盐糖实际用量闭环校准后的单份营养（三层校准第二层）"
SOURCE_NOTE_CALIBRATED_CAPITA = "闭环校准后的该菜人均摄入（三层校准第二层）"
SOURCE_NOTE_SAMPLED = "每周抽样称重实测的单份营养（三层校准第三层）"

#: 反推出来的系数超出这个范围，就不是「调味料手感」能解释的了，
#: 更可能是配方本身录错——这时候不要硬套，标记出来让人工核对。
SUSPECT_FACTOR_LOW = Decimal("0.5")
SUSPECT_FACTOR_HIGH = Decimal("2.0")

#: 抽样实测值的误差区间下限：再怎么准，也不该声称误差是 0
SAMPLED_MIN_TOLERANCE = Decimal("0.05")

#: 每日采集里能拿到实际用量的调味料类别 → daily_logs 上的字段
CLOSURE_ACTUAL_FIELD: dict[SeasoningCategory, str] = {
    SeasoningCategory.EDIBLE_OIL: "oil_total_g",
    SeasoningCategory.SALT: "salt_total_g",
    SeasoningCategory.SUGAR: "sugar_total_g",
}


@dataclass
class ComputeReport:
    """一次计算的写入统计，供调用方断言与输出。"""

    menu_days: int = 0
    dishes: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0

    def merge(self, other: ComputeReport) -> ComputeReport:
        return ComputeReport(
            menu_days=self.menu_days + other.menu_days,
            dishes=self.dishes + other.dishes,
            created=self.created + other.created,
            updated=self.updated + other.updated,
            unchanged=self.unchanged + other.unchanged,
        )

    def record(self, action: str) -> None:
        if action == "created":
            self.created += 1
        elif action == "updated":
            self.updated += 1
        else:
            self.unchanged += 1

    @property
    def rows(self) -> int:
        return self.created + self.updated + self.unchanged

    def describe(self) -> str:
        return (
            f"菜单日 {self.menu_days} 天，覆盖菜品 {self.dishes} 道；"
            f"营养结果共 {self.rows} 条（新增 {self.created}、更新 {self.updated}、"
            f"未变 {self.unchanged}）"
        )


def compute_menu_day(session: Session, *, on_date: date, meal_type: MealType) -> ComputeReport:
    """计算某天某一餐的全部营养结果。"""
    report = ComputeReport()

    menu_day = repository.load_menu_day(session, on_date, meal_type)
    if menu_day is None:
        return report
    report.menu_days = 1

    recipes = repository.load_recipes(session, repository.load_menu_dish_ids(session, menu_day.id))
    report.dishes = len(recipes)

    daily_log = repository.load_daily_log(session, on_date, meal_type)
    log_items = repository.load_daily_log_items(session, daily_log.id) if daily_log else {}

    for dish_id, recipe in recipes.items():
        result = engine.compute_theoretical_per_serving(recipe)

        report.record(
            repository.upsert_dish_nutrition(
                session,
                dish_id=dish_id,
                on_date=on_date,
                meal_type=meal_type,
                caliber=NutrientCaliber.PER_SERVING,
                value_type=NutritionValueType.THEORETICAL,
                nutrients=result.per_serving,
                uncertainty=_uncertainty_payload(
                    result.per_serving, missing_nutrients=result.missing_nutrients
                ),
                trace=result.trace,
                source_note=SOURCE_NOTE_PER_SERVING,
            )
        )

        item = log_items.get(dish_id)
        if daily_log is None or item is None:
            continue

        report.record(
            _store_per_capita(
                session,
                on_date=on_date,
                meal_type=meal_type,
                dish_id=dish_id,
                per_serving=result.per_serving,
                source_trace=result.trace,
                missing_nutrients=result.missing_nutrients,
                servings_produced=item.servings_produced,
                leftover_ratio=item.leftover_ratio,
                diner_count=daily_log.diner_count,
            )
        )

    session.flush()
    return report


def compute_recent_days(session: Session, *, days: int) -> ComputeReport:
    """计算最近若干天（含今天）的营养结果，用于准备演示数据。"""
    today = datetime.now(get_settings().timezone).date()
    start = today - timedelta(days=days - 1)

    total = ComputeReport()
    for menu_day in repository.list_menu_days_between(session, start, today):
        total = total.merge(
            compute_menu_day(session, on_date=menu_day.date, meal_type=menu_day.meal_type)
        )
    session.commit()
    logger.info("营养计算完成：%s", total.describe())
    return total


def recompute_dish_nutrition(session: Session, dish_id: UUID) -> ComputeReport:
    """重算某道菜在**所有供应过它的日子**里的营养结果。

    配方一改，历史结果不能只改最近一天——公开大屏看的是当天，
    而看板、抽样对比、预测回测看的都是历史，几处必须一起对齐。
    """
    menu_days = repository.list_menu_days_for_dish(session, dish_id)
    total = ComputeReport()
    for menu_day in menu_days:
        total = total.merge(
            compute_menu_day(session, on_date=menu_day.date, meal_type=menu_day.meal_type)
        )
    session.commit()
    return total


@dataclass
class ClosureFactorRow:
    """一种烹饪方式下，油盐糖各自的校准系数与它算出来的依据。"""

    cooking_method: CookingMethod
    #: 类别代码 → 系数
    coefficients: dict[str, str]
    #: 类别代码 → 当日该烹饪方式按配方推算的用量（克）
    theoretical_g: dict[str, str]
    #: 类别代码 → 当日实际用量（克）；拿不到实际值的类别为空
    actual_g: dict[str, str | None]


@dataclass
class SamplingCorrectionRow:
    """第三层抽样纠偏作用到某道菜上的整体修正比。"""

    dish_id: UUID
    dish_name: str
    #: 修正比本身，例如 1.0738
    overall: Decimal
    #: 这条修正来自「只针对这道菜」还是「针对整类烹饪方式」
    scope: str


@dataclass
class ClosureReport:
    date: date
    meal_type: MealType
    factors: list[ClosureFactorRow]
    calibrated_rows: int
    note: str
    #: 本次实际叠加到菜品上的第三层抽样修正
    sampling_corrections: list[SamplingCorrectionRow]

    def describe(self) -> str:
        return f"{self.date} {self.meal_type.label}：{len(self.factors)} 类烹饪方式，校准结果 {self.calibrated_rows} 条"


def compute_daily_closure(session: Session, *, on_date: date, meal_type: MealType) -> ClosureReport:
    """第二层 当日闭环：用当天实际油盐糖总量校正配方推算值。

    按烹饪方式分组、油盐糖各算各的：蒸菜压根不加油，拿炒菜的系数去缩放它没有意义；
    而多放油很常见、多放糖不常见，两者偏差幅度本来就不一样，合成一个系数需要一个
    加权方式，任何一种加权都没有客观依据。

    系数最终**只作用在调味料贡献上**，食材部分原样保留——理由见 engine.apply_calibration。
    """
    menu_day = repository.load_menu_day(session, on_date, meal_type)
    daily_log = repository.load_daily_log(session, on_date, meal_type)
    if menu_day is None:
        raise BusinessRuleError("当天没有菜单，先确认供应的菜品再校准")
    if daily_log is None:
        raise BusinessRuleError("当天没有每日记录，先采集油盐糖实际用量再校准")

    recipes = repository.load_recipes(session, repository.load_menu_dish_ids(session, menu_day.id))
    log_items = repository.load_daily_log_items(session, daily_log.id)

    # 按配方推算：每种烹饪方式下，各调味料类别一共该用多少克
    computed: dict[CookingMethod, dict[SeasoningCategory, Decimal]] = defaultdict(
        lambda: defaultdict(lambda: Decimal("0"))
    )
    for dish_id, recipe in recipes.items():
        item = log_items.get(dish_id)
        servings = item.servings_produced if item is not None else Decimal("0")
        if servings <= 0:
            continue
        for line in recipe.seasonings:
            computed[recipe.cooking_method][line.seasoning.category] += line.quantity_g * servings

    # 当天出现过的每种烹饪方式都要有系数。蒸菜压根不放油盐糖，配方推算总量为 0、
    # 系数自然全是 1，但**仍然要给出校准结果**——否则「当天校准后的完整结果」里
    # 会缺几道菜，界面上看着像校准失败，而不是「这道菜不需要校准」。
    for recipe in recipes.values():
        computed.setdefault(recipe.cooking_method, {})

    rows: list[ClosureFactorRow] = []
    factors_by_method: dict[CookingMethod, engine.CalibrationFactors] = {}
    for method, by_category in computed.items():
        coefficients: dict[str, Decimal] = {}
        for category, theoretical_g in by_category.items():
            field_name = CLOSURE_ACTUAL_FIELD.get(category)
            actual = getattr(daily_log, field_name) if field_name else None
            if actual is None or theoretical_g <= 0:
                # 拿不到实际值的类别不缩放（例如酱油、淀粉这类不逐日采集的）
                coefficients[category.value] = Decimal("1")
                continue
            coefficients[category.value] = quantize(actual / theoretical_g, 4)

        factors_by_method[method] = engine.CalibrationFactors(
            by_category={SeasoningCategory(code): value for code, value in coefficients.items()},
            source_note=f"当日闭环：{method.label}",
        )
        encoded: dict[str, Any] = {code: str(value) for code, value in coefficients.items()}
        rows.append(
            ClosureFactorRow(
                cooking_method=method,
                coefficients=encoded,
                theoretical_g={
                    category.value: str(quantize(theoretical_g, 2))
                    for category, theoretical_g in by_category.items()
                },
                actual_g={
                    category.value: (
                        None
                        if CLOSURE_ACTUAL_FIELD.get(category) is None
                        else str(getattr(daily_log, CLOSURE_ACTUAL_FIELD[category]))
                    )
                    for category in by_category
                },
            )
        )
        repository.replace_calibration_factors(
            session,
            on_date=on_date,
            meal_type=meal_type,
            cooking_method=method,
            source=CalibrationSource.DAILY_CLOSURE,
            coefficients=encoded,
            basis_note=(
                f"当日实际用量 ÷ 配方推算用量；"
                f"{method.label}："
                + "、".join(
                    f"{category.label} {quantize(theoretical_g, 1)}g"
                    for category, theoretical_g in by_category.items()
                )
            ),
        )

    # 第三层抽样纠偏留下的整体系数：把它叠到第二层的系数上，三层的成果才真的汇到一处。
    # 每类烹饪方式只查一次库，避免逐道菜重复查询。
    corrections_by_method = {
        method: repository.latest_sampling_corrections(
            session, cooking_method=method, on_or_before=on_date
        )
        for method in {recipe.cooking_method for recipe in recipes.values()}
    }
    overall_by_dish: dict[UUID, Decimal] = {}
    sampling_rows: list[SamplingCorrectionRow] = []
    for dish_id, recipe in recipes.items():
        per_dish, per_method = corrections_by_method.get(recipe.cooking_method, ({}, None))
        if dish_id in per_dish:
            correction, scope = per_dish[dish_id], "DISH"
        elif per_method is not None:
            correction, scope = per_method, "COOKING_METHOD"
        else:
            continue
        overall_by_dish[dish_id] = correction
        sampling_rows.append(
            SamplingCorrectionRow(
                dish_id=dish_id,
                dish_name=recipe.dish_name,
                overall=correction,
                scope=scope,
            )
        )

    calibrated_rows = _store_calibrated_day(
        session,
        on_date=on_date,
        meal_type=meal_type,
        recipes=recipes,
        log_items=log_items,
        diner_count=daily_log.diner_count,
        factors_by_method=factors_by_method,
        overall_by_dish=overall_by_dish,
    )
    session.commit()
    logger.info("当日闭环校准完成：%s", rows and f"{len(rows)} 类烹饪方式")
    return ClosureReport(
        date=on_date,
        meal_type=meal_type,
        factors=rows,
        calibrated_rows=calibrated_rows,
        sampling_corrections=sampling_rows,
        note=(
            "系数 = 当日实际用量 ÷ 按配方推算的用量，只作用在调味料贡献上；"
            "食材部分保持不变。酱油、淀粉等不逐日采集的调味料不参与校准。"
            "已有抽样纠偏的菜品在此基础上再乘一个抽样修正比（第三层）。"
        ),
    )


def _store_calibrated_day(
    session: Session,
    *,
    on_date: date,
    meal_type: MealType,
    recipes: dict[UUID, engine.DishRecipe],
    log_items: dict[UUID, Any],
    diner_count: int,
    factors_by_method: dict[CookingMethod, engine.CalibrationFactors],
    overall_by_dish: dict[UUID, Decimal] | None = None,
) -> int:
    """把校准后的单份与人均结果落库，逐条与理论值并存，便于对比。

    缩放分两段乘在调味料贡献上：第二层按烹饪方式给的是「今天这批菜整体比配方多放了多少」，
    第三层按菜品给的是「这道菜自己长期偏多少」。两者量纲不同，所以是相乘而不是取其一。
    """
    per_dish_overall = overall_by_dish or {}
    rows = 0
    for dish_id, recipe in recipes.items():
        base = engine.compute_theoretical_per_serving(recipe)
        method_factors = factors_by_method.get(recipe.cooking_method)
        if method_factors is None:
            continue
        overall = per_dish_overall.get(dish_id, Decimal("1"))
        factors = engine.CalibrationFactors(
            by_category=method_factors.by_category,
            overall=overall,
            source_note=method_factors.source_note,
        )
        per_serving = engine.apply_calibration(base, factors)
        uncertainty = _uncertainty_payload(per_serving, missing_nutrients=base.missing_nutrients)
        trace = {
            **base.trace,
            "layer": "当日闭环校准",
            "calibration": {
                "daily_closure": {
                    category.value: str(value) for category, value in factors.by_category.items()
                },
                "sampling_overall": str(overall),
                "applies_to": ("调味料贡献 = Σ(类别贡献 × 当日闭环系数) × 抽样修正；食材部分不变"),
                "theoretical_per_serving": base.per_serving.as_trace(),
            },
        }
        repository.upsert_dish_nutrition(
            session,
            dish_id=dish_id,
            on_date=on_date,
            meal_type=meal_type,
            caliber=NutrientCaliber.PER_SERVING,
            value_type=NutritionValueType.CALIBRATED,
            nutrients=per_serving,
            uncertainty=uncertainty,
            trace=trace,
            source_note=SOURCE_NOTE_CALIBRATED,
        )
        rows += 1

        item = log_items.get(dish_id)
        if item is None:
            continue
        rows += 1
        _store_per_capita(
            session,
            on_date=on_date,
            meal_type=meal_type,
            dish_id=dish_id,
            per_serving=per_serving,
            source_trace=trace,
            missing_nutrients=base.missing_nutrients,
            servings_produced=item.servings_produced,
            leftover_ratio=item.leftover_ratio,
            diner_count=diner_count,
            value_type=NutritionValueType.CALIBRATED,
            source_note=SOURCE_NOTE_CALIBRATED_CAPITA,
        )
    session.flush()
    return rows


def preview_per_serving(session: Session, dish_ids: Sequence[UUID]) -> dict[UUID, NutrientVector]:
    """按当前配方现算单份营养，**不落库**。

    服务的是「还没被排进过菜单」的菜品：它没有 `dish_nutritions` 快照可读，
    但配方已经能算出营养值。单份理论值只取决于配方本身，与「哪天供应」无关，
    所以这里算出来的与将来落库的结果一致；区别只在于没有日期，也就不可追溯，
    因此只用于列表摘要这种即时展示，不作为正式结果。
    """
    previews: dict[UUID, NutrientVector] = {}
    for dish_id, recipe in repository.load_recipes(session, dish_ids).items():
        if not recipe.ingredients and not recipe.seasonings:
            # 没有配方明细就没有可算的东西，交给上层显示「无配方」
            continue
        previews[dish_id] = engine.compute_theoretical_per_serving(recipe).per_serving
    return previews


def _store_per_capita(
    session: Session,
    *,
    on_date: date,
    meal_type: MealType,
    dish_id: UUID,
    per_serving: NutrientVector,
    source_trace: dict[str, Any],
    missing_nutrients: tuple[str, ...],
    servings_produced: Decimal,
    leftover_ratio: Decimal | None,
    diner_count: int,
    value_type: NutritionValueType = NutritionValueType.THEORETICAL,
    source_note: str = SOURCE_NOTE_PER_CAPITA,
) -> str:
    per_capita = engine.compute_theoretical_per_capita(
        per_serving,
        servings_produced=servings_produced,
        leftover_ratio=leftover_ratio,
        diner_count=diner_count,
    )
    # 人均口径的区间比单份更宽：出餐份数、剩余比例与就餐人次本身都不精确
    extra = engine.PER_CAPITA_EXTRA_TOLERANCE
    trace: dict[str, Any] = {
        **source_trace,
        "caliber": NutrientCaliber.PER_CAPITA.value,
        "tolerance": {
            "base": str(engine.BASE_TOLERANCE),
            "applied": str(engine.tolerance_for(len(missing_nutrients), extra=extra)),
            "reason": f"在单份推算误差之上，再叠加份数、剩余比例与人次数量的估计误差 +{extra}",
        },
        "per_capita_basis": {
            "formula": "人均摄入 = 单份营养 × 出餐份数 × (1 − 剩余比例) ÷ 就餐人次",
            "per_serving": per_serving.as_trace(),
            "servings_produced": str(servings_produced),
            "leftover_ratio": None if leftover_ratio is None else str(leftover_ratio),
            "diner_count": diner_count,
        },
    }
    return repository.upsert_dish_nutrition(
        session,
        dish_id=dish_id,
        on_date=on_date,
        meal_type=meal_type,
        caliber=NutrientCaliber.PER_CAPITA,
        value_type=value_type,
        nutrients=per_capita,
        uncertainty=_uncertainty_payload(
            per_capita, missing_nutrients=missing_nutrients, extra_tolerance=extra
        ),
        trace=trace,
        source_note=source_note,
    )


def _uncertainty_payload(
    nutrients: NutrientVector,
    *,
    missing_nutrients: tuple[str, ...],
    extra_tolerance: Decimal = Decimal("0"),
) -> dict[str, Any]:
    ranges = engine.build_uncertainty(
        nutrients, missing_nutrients=missing_nutrients, extra_tolerance=extra_tolerance
    )
    return {
        "note": "第一层基准误差 ±15%，成分数据缺失时逐项放宽，人均口径另叠加份数与人次误差",
        "tolerance": str(engine.tolerance_for(len(missing_nutrients), extra=extra_tolerance)),
        "missing_nutrients": list(missing_nutrients),
        "ranges": {field: interval.as_dict() for field, interval in ranges.items()},
    }


# ---------------------------------------------------------------------------
# 第三层 抽样纠偏
# ---------------------------------------------------------------------------
@dataclass
class SampleReport:
    dish_id: UUID
    dish_name: str
    on_date: date
    meal_type: MealType
    measured: engine.NutrientVector
    computed: engine.NutrientVector
    #: 每项指标相对推算值的偏差比例（实测 − 推算）÷ 推算
    deviations: dict[str, str]
    #: 由能量反推出的调味料整体系数；无法反推时为空
    overall_factor: Decimal | None
    applied: bool
    suspect_recipe: bool
    note: str


def record_sample(
    session: Session,
    *,
    dish_id: UUID,
    on_date: date,
    meal_type: MealType,
    measured: engine.NutrientVector,
    scope: str,
    note: str | None = None,
    created_by: UUID | None = None,
) -> SampleReport:
    """第三层 抽样纠偏：用称重实测反推调味料该乘多少。

    推理链条只有一句：**食材是按配方称重的，信任它；差额全部归给调味料**。
    所以「要让总量对上实测值，调味料那一块该乘多少」是可以直接算出来的：

        系数 = (实测能量 − 食材能量) ÷ 配方里的调味料能量

    系数落在合理范围内才写入并生效。超出范围说明这不是调味料手感的问题，
    更可能是配方本身录错了——这时只存实测证据并标记出来，不硬套系数，
    免得把一个错误的配方「校准」成一个看起来自洽的错误值。
    """
    recipe = repository.load_recipes(session, [dish_id]).get(dish_id)
    if recipe is None:
        raise NotFoundError("菜品不存在")
    if not recipe.ingredients and not recipe.seasonings:
        raise BusinessRuleError("这道菜还没有配方，没有可比对的基准")

    base = engine.compute_theoretical_per_serving(recipe)
    computed = base.per_serving

    deviations: dict[str, str] = {
        field: str(
            quantize(
                (getattr(measured, field) - getattr(computed, field)) / getattr(computed, field),
                4,
            )
        )
        if getattr(computed, field) > 0
        else "0.0000"
        for field in engine.NUTRIENT_FIELDS
    }

    seasoning_energy = sum(vector.energy_kcal for vector in base.seasoning_by_category.values())
    overall_factor: Decimal | None = None
    if seasoning_energy > 0:
        overall_factor = quantize(
            (measured.energy_kcal - base.ingredient_part.energy_kcal) / seasoning_energy, 4
        )

    suspect = overall_factor is None or not (
        SUSPECT_FACTOR_LOW <= overall_factor <= SUSPECT_FACTOR_HIGH
    )
    # 实测与推算的差距有多大，就承认多大的把握；但不声称误差是 0
    observed = max(
        (abs(Decimal(value)) for value in deviations.values()), default=SAMPLED_MIN_TOLERANCE
    )
    tolerance = max(observed, SAMPLED_MIN_TOLERANCE)

    trace: dict[str, Any] = {
        "engine": engine.ENGINE_NAME,
        "engine_version": engine.ENGINE_VERSION,
        "layer": "抽样纠偏实测",
        "dish_name": recipe.dish_name,
        "recipe_version": recipe.recipe_version,
        "computed_per_serving": computed.as_trace(),
        "measured_per_serving": measured.as_trace(),
        "deviations": deviations,
        "ingredient_part": base.ingredient_part.as_trace(),
        "seasoning_part": {
            category.value: vector.as_trace()
            for category, vector in base.seasoning_by_category.items()
        },
        "derived_overall_factor": None if overall_factor is None else str(overall_factor),
        "tolerance": {
            "base": str(engine.BASE_TOLERANCE),
            "applied": str(tolerance),
            "reason": f"由实测偏差决定；实测与推算最大相差 {observed}",
        },
        "applied": not suspect,
        "suspect_recipe": suspect,
        "note": note,
    }

    repository.upsert_dish_nutrition(
        session,
        dish_id=dish_id,
        on_date=on_date,
        meal_type=meal_type,
        caliber=NutrientCaliber.PER_SERVING,
        value_type=NutritionValueType.SAMPLED,
        nutrients=measured,
        uncertainty={
            "note": "抽样实测值；区间由实测与推算的偏差决定",
            "tolerance": str(tolerance),
            "missing_nutrients": [],
            "ranges": {
                field: interval.as_dict()
                for field, interval in engine.build_uncertainty(
                    measured, extra_tolerance=tolerance
                ).items()
            },
        },
        trace=trace,
        source_note=SOURCE_NOTE_SAMPLED,
    )

    if not suspect and overall_factor is not None:
        repository.replace_calibration_factors(
            session,
            on_date=on_date,
            meal_type=meal_type,
            cooking_method=recipe.cooking_method,
            source=CalibrationSource.SAMPLING,
            coefficients={"OVERALL": str(overall_factor)},
            dish_id=dish_id if scope == "DISH" else None,
            basis_note=(
                f"抽样实测反推：(实测能量 {measured.energy_kcal} − 食材能量 "
                f"{base.ingredient_part.energy_kcal}) ÷ 调味料能量 {seasoning_energy}"
                f" = {overall_factor}"
            ),
            created_by=created_by,
        )

    session.commit()
    logger.info(
        "抽样纠偏：%s 系数 %s%s",
        recipe.dish_name,
        overall_factor,
        "（疑似配方有误，未套用）" if suspect else "",
    )
    return SampleReport(
        dish_id=dish_id,
        dish_name=recipe.dish_name,
        on_date=on_date,
        meal_type=meal_type,
        measured=measured,
        computed=computed,
        deviations=deviations,
        overall_factor=overall_factor,
        applied=not suspect,
        suspect_recipe=suspect,
        note=(
            "已按实测值记录该菜单份营养（SAMPLED），并留下一张可复核的调味料系数"
            if not suspect
            else "实测与推算差距超出调味料能解释的范围，已保留实测证据但未套用系数，"
            "建议核对这道菜的配方用量"
        ),
    )

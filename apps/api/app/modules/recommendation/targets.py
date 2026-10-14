"""把膳食基准折算成「这一餐要满足什么」（纯函数）。

两条口径必须分开讲清楚，否则目标区间会变成一堆没有依据的数字：

1. **能量与三大营养素按餐次占比折算**。它们是「要给够」的东西，一餐该承担全天的一部分。
   午餐取 40%（早 30 / 午 40 / 晚 30，可配置）。供能比取《中国居民膳食指南（2022）》的
   蛋白质 10–15%、脂肪 20–30%、碳水化合物 50–65%，每克产能取 4 / 9 / 4 千卡，
   由「能量目标 × 供能比 ÷ 每克产能」反推克数区间。

2. **油、盐、糖取每日上限，不按餐次折算**。需求里写的就是「直接引用每日基准」。
   这不是偷懒：按 40% 折算，午餐的食盐上限是 2 克，而任何五道菜的合计都在 4 克以上——
   一餐折算的口径会让模型必然无解。而「一餐不超过全天上限」是全天合规的**充分条件**，
   它从不放松要求。真实差距（按折算应 ≤2 克、实际 4.5 克）放在差距分析里如实报出。
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.core.config import get_settings
from app.modules.nutrition.models import NutritionStandard
from app.modules.recommendation.solver import PlanTarget
from app.shared.enums import MealType, StandardCode

#: 供能比区间，引《中国居民膳食指南（2022）》
ENERGY_RATIOS: dict[str, tuple[Decimal, Decimal]] = {
    "protein_g": (Decimal("0.10"), Decimal("0.15")),
    "fat_g": (Decimal("0.20"), Decimal("0.30")),
    "carb_g": (Decimal("0.50"), Decimal("0.65")),
}

#: 每克产能（千卡）
KCAL_PER_GRAM: dict[str, Decimal] = {
    "protein_g": Decimal("4"),
    "fat_g": Decimal("9"),
    "carb_g": Decimal("4"),
}

DEFAULT_MEAL_SHARE = Decimal("0.4")


def meal_share(meal_type: MealType) -> Decimal:
    """这一餐占全天的能量比例。"""
    settings = get_settings()
    lunch = Decimal(str(settings.nutrition_meal_share_lunch))
    if meal_type is MealType.LUNCH:
        return lunch
    # 早餐与晚餐平分剩下的部分：改了午餐比例，另外两餐跟着变，不用改三处
    return ((Decimal("1") - lunch) / 2).quantize(Decimal("0.01"))


def energy_targets(meal_type: MealType) -> tuple[PlanTarget, tuple[PlanTarget, ...]]:
    """能量区间，以及由它反推出来的三大营养素区间。"""
    settings = get_settings()
    share = meal_share(meal_type)
    full_max = Decimal(str(settings.nutrition_energy_target_kcal))
    full_min = Decimal(str(settings.nutrition_energy_target_min_kcal))
    energy = PlanTarget(
        code="energy_kcal",
        label="能量",
        unit="千卡",
        lower=(full_min * share).quantize(Decimal("1"), rounding=ROUND_HALF_UP),
        upper=(full_max * share).quantize(Decimal("1"), rounding=ROUND_HALF_UP),
    )
    macro_targets = tuple(
        _macro_target(field, full_min, full_max, share) for field in ENERGY_RATIOS
    )
    return energy, macro_targets


def _macro_target(field: str, full_min: Decimal, full_max: Decimal, share: Decimal) -> PlanTarget:
    low_ratio, high_ratio = ENERGY_RATIOS[field]
    per_gram = KCAL_PER_GRAM[field]
    lower = full_min * low_ratio / per_gram * share
    upper = full_max * high_ratio / per_gram * share
    label, unit = {
        "protein_g": ("蛋白质", "克"),
        "fat_g": ("脂肪", "克"),
        "carb_g": ("碳水化合物", "克"),
    }[field]
    return PlanTarget(
        code=field,
        label=label,
        unit=unit,
        lower=lower.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP),
        upper=upper.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP),
    )


#: 三类调料在基准表里的代码 → 求解器里的指标代码
SEASONING_TARGET_CODES: dict[StandardCode, str] = {
    StandardCode.EDIBLE_OIL: "EDIBLE_OIL",
    StandardCode.SALT: "SALT",
    StandardCode.ADDED_SUGAR: "ADDED_SUGAR",
}


def seasoning_targets(standards: list[NutritionStandard]) -> tuple[PlanTarget, ...]:
    """油盐糖的每日上限，原样使用。

    基准表里的烹调油是 25~30 克的**区间**（推荐摄入量），但对一餐来说只能当下限用上限：
    要求某一餐必须用够 25 克油，等于逼后厨多倒油，显然不是指南的本意。
    所以这里只取上限。
    """
    targets: list[PlanTarget] = []
    for standard in standards:
        code = SEASONING_TARGET_CODES.get(standard.code)
        if code is None or standard.target_max is None:
            continue
        targets.append(
            PlanTarget(
                code=code,
                label=standard.name,
                unit=standard.unit,
                lower=None,
                upper=Decimal(standard.target_max),
            )
        )
    return tuple(targets)


def min_ingredient_kinds(standards: list[NutritionStandard]) -> int:
    """食物种类的下限。种类数是「几种」而不是「多少量」，因此不按餐次折算。"""
    for standard in standards:
        if standard.code is StandardCode.FOOD_VARIETY and standard.target_min is not None:
            return int(standard.target_min)
    return 0


def build_targets(
    meal_type: MealType, standards: list[NutritionStandard]
) -> tuple[tuple[PlanTarget, ...], dict[str, object]]:
    """组装求解器的目标区间，同时给出一份可展示的说明。"""
    settings = get_settings()
    energy, macros = energy_targets(meal_type)
    targets = (energy, *macros, *seasoning_targets(standards))
    explanation: dict[str, object] = {
        "meal_share": str(meal_share(meal_type)),
        "energy_target_kcal": settings.nutrition_energy_target_kcal,
        "energy_target_min_kcal": settings.nutrition_energy_target_min_kcal,
        "energy_source": ("全天能量目标为演示值，待核实：需以《学生餐营养指南》等标准原文替换"),
        "energy_verified": False,
        "macro_source": (
            "由能量目标 × 供能比 ÷ 每克产能反推；供能比取《中国居民膳食指南（2022）》"
            "蛋白质 10–15%、脂肪 20–30%、碳水化合物 50–65%"
        ),
        "seasoning_source": (
            "油盐糖取每日上限、不按餐次折算——按 40% 折算的一餐上限在现有配方下必然无解；"
            "「一餐不超全天上限」是全天合规的充分条件"
        ),
    }
    return targets, explanation

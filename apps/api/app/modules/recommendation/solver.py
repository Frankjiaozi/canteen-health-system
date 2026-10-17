"""菜单组合优化（纯函数，不碰数据库）。

这是一个带约束的组合优化问题，不是文本生成任务。写成整数规划而不是启发式搜索，
是为了让「满足全部硬约束」这句话**可验证**——启发式只能靠穷举去碰。

用 PuLP 自带的 CBC 求解器，不需要额外装系统组件。
**注意别升到 PuLP 4.x**：那一版不再自带求解器（`listSolvers` 是空的），参数名也换了。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

import pulp

from app.shared.enums import CookingMethod, DishCategory

SOLVER_VERSION = "menu-ilp-v1"

#: 求解时间上限。候选集只有几十道菜，这个上限是兜底而不是常态。
TIME_LIMIT_SECONDS = 10

#: 模型里的变量名 → 候选菜上的字段名。油盐糖用的是调味料用量，不是营养素。
FIELD_BY_CODE: dict[str, str] = {
    "energy_kcal": "energy_kcal",
    "protein_g": "protein_g",
    "fat_g": "fat_g",
    "carb_g": "carb_g",
    "sodium_mg": "sodium_mg",
    "EDIBLE_OIL": "oil_g",
    "SALT": "salt_g",
    "ADDED_SUGAR": "sugar_g",
}


class InfeasibleError(Exception):
    """解不出来。带上最可能是哪条约束卡住了——只说「无解」对使用者毫无帮助。"""

    def __init__(self, status: str, conflicts: list[str]) -> None:
        self.status = status
        self.conflicts = conflicts
        super().__init__(f"{status}：{'；'.join(conflicts)}")


@dataclass(frozen=True, slots=True)
class CandidateDish:
    """求解器眼里的一个候选。营养与调料用量都是**单份**口径。"""

    dish_id: UUID
    name: str
    category: DishCategory
    cooking_method: CookingMethod
    energy_kcal: Decimal
    protein_g: Decimal
    fat_g: Decimal
    carb_g: Decimal
    sodium_mg: Decimal
    oil_g: Decimal
    salt_g: Decimal
    sugar_g: Decimal
    cost_per_serving: Decimal
    popularity: Decimal
    ingredient_ids: frozenset[UUID]


@dataclass(frozen=True, slots=True)
class PlanTarget:
    """一项指标的区间。`lower` 为空表示只考核上限。

    `hard` 决定它是**必须满足的约束**还是**尽量逼近的目标**，两者在模型里的地位完全不同：

    - 硬约束：写进约束条件，越界就是无解。
    - 目标：进目标函数，按偏离区间中点的相对量罚一笔分；满足不了也不会无解。

    营养区间默认走「目标」而不是硬约束，是实测逼出来的：这套菜谱的蛋白质供能比约 18%，
    高于指南的 10–15%，于是「能量够到 720」与「蛋白质不超 30 克」互相排斥——
    两者都当硬约束就是无解。指南的供能比是**建议目标**不是安全上限，
    而钠、油、糖才是必须卡住的东西，所以后者保持硬约束。
    """

    code: str
    label: str
    unit: str
    lower: Decimal | None
    upper: Decimal | None
    hard: bool = False


@dataclass(frozen=True, slots=True)
class PlanConstraints:
    """硬约束，全部来自可配置的膳食基准与预算。"""

    targets: tuple[PlanTarget, ...]
    budget: Decimal
    diner_count: int
    dish_count_min: int
    dish_count_max: int
    serving_ratio_min: Decimal
    serving_ratio_max: Decimal
    max_method_ratio: Decimal
    min_ingredient_kinds: int
    #: 各类菜的道数上下限。少了它，求解器会给出「两道汤 + 三道蛋菜」这种菜单——
    #: 营养上挑不出毛病，但不是一餐饭。
    category_min: dict[DishCategory, int]
    category_max: dict[DishCategory, int]
    #: 逐菜份数由外部给定（例如预测份数）。给了就不再由推荐决定份量——
    #: 份数该由「这道菜明天实际会出多少」决定，那是预测的活，不是配餐的活。
    fixed_servings: dict[UUID, Decimal] = field(default_factory=dict)
    excluded_dish_ids: frozenset[UUID] = frozenset()


@dataclass(frozen=True, slots=True)
class PlanWeights:
    """目标函数三项的权重：营养偏差最小、成本可控、受欢迎度最高。

    成本权重刻意小于营养：成本项是「占预算的比例」（0~1），而营养偏差是相对偏差
    （通常在 0.05 上下），两者等权时成本会把营养挤到边界上——实测权重都取 1 时，
    求解器会交出能量刚踩下限、尽量省钱的菜单。0.3 是让两者量级可比的经验值。
    """

    nutrition: Decimal = Decimal("1")
    cost: Decimal = Decimal("0.3")
    popularity: Decimal = Decimal("0.5")


@dataclass(frozen=True, slots=True)
class PlannedDish:
    dish_id: UUID
    name: str
    servings: Decimal
    cost: Decimal


@dataclass(frozen=True, slots=True)
class PlanResult:
    items: list[PlannedDish]
    #: 人均供给，按指标代码索引
    per_capita: dict[str, Decimal]
    cost: Decimal
    #: 贴边的约束，同时也是「为什么给出这份菜单」的答案之一
    binding: list[str] = field(default_factory=list)
    solver_status: str = ""


def solve_menu(
    candidates: list[CandidateDish],
    constraints: PlanConstraints,
    *,
    weights: PlanWeights | None = None,
    time_limit: int = TIME_LIMIT_SECONDS,
) -> PlanResult:
    """求解一份菜单：选哪些菜、各做多少份。

    决策变量是「选不选这道菜」（0/1）与「做多少份」（连续），
    因此「换一道菜」和「同一道菜多做点」在模型里是分开的两件事。
    """
    if constraints.diner_count <= 0:
        raise InfeasibleError("输入不完整", ["就餐人次必须大于 0，否则人均供给没有意义"])

    excluded = set(constraints.excluded_dish_ids)
    usable = [dish for dish in candidates if dish.dish_id not in excluded]
    if not usable:
        raise InfeasibleError("没有可用的候选菜品", ["所有候选都被「不连续两日重复」排除了"])

    weight = weights or PlanWeights()
    problem = pulp.LpProblem("menu", pulp.LpMinimize)
    diners = Decimal(constraints.diner_count)
    upper_servings = diners * constraints.serving_ratio_max
    lower_servings = diners * constraints.serving_ratio_min

    pick: dict[UUID, pulp.LpVariable] = {}
    portions: dict[UUID, pulp.LpVariable] = {}
    for index, dish in enumerate(usable):
        pick[dish.dish_id] = pulp.LpVariable(f"x_{index}", cat="Binary")
        fixed = constraints.fixed_servings.get(dish.dish_id)
        if fixed is not None:
            # 份数已经给定：选了就按这个份数做，不选就是 0。它不再是决策变量，
            # 于是模型只剩「选哪些菜」这一件事——这正是推荐该回答的问题。
            portions[dish.dish_id] = pulp.LpVariable(f"s_{index}", lowBound=0, upBound=float(fixed))
            problem += portions[dish.dish_id] == float(fixed) * pick[dish.dish_id]
            continue
        portions[dish.dish_id] = pulp.LpVariable(
            f"s_{index}", lowBound=0, upBound=float(upper_servings)
        )
        # 不选就不可能做；选了也要做到下限——否则求解器会用「做 0.3 份」绕开约束
        problem += portions[dish.dish_id] <= float(upper_servings) * pick[dish.dish_id]
        problem += portions[dish.dish_id] >= float(lower_servings) * pick[dish.dish_id]

    def per_capita(field_name: str) -> pulp.LpAffineExpression:
        return pulp.lpSum(
            float(getattr(dish, field_name)) * portions[dish.dish_id] for dish in usable
        ) / float(diners)

    slacks: list[pulp.LpAffineExpression] = []
    for target in constraints.targets:
        field_name = FIELD_BY_CODE.get(target.code)
        if field_name is None:
            continue
        expression = per_capita(field_name)
        scale = float(_scale_of(target))
        if target.hard:
            # 硬约束：越界即无解，并指出卡在哪条（比悄悄给一份越界的菜单诚实）
            if target.lower is not None:
                problem += expression >= float(target.lower)
            if target.upper is not None:
                problem += expression <= float(target.upper)
        else:
            # 目标：偏离区间多远就罚多少（区间内不罚）。没有区间的单边指标按边界罚。
            shortfall = pulp.LpVariable(f"lo_{target.code}", lowBound=0)
            excess = pulp.LpVariable(f"hi_{target.code}", lowBound=0)
            if target.lower is not None:
                problem += expression + shortfall >= float(target.lower)
                slacks.append(shortfall * (float(weight.nutrition) / scale))
            if target.upper is not None:
                problem += expression - excess <= float(target.upper)
                slacks.append(excess * (float(weight.nutrition) / scale))
        # 区间取中而不是贴着下限：只要求「落在区间内」时，求解器会一路踩到边界，
        # 交出一份「刚刚好达标」的菜单。这一项把它拉向区间中间。
        midpoint = _midpoint(target)
        if midpoint is not None:
            away = pulp.LpVariable(f"mid_{target.code}", lowBound=0)
            problem += expression - float(midpoint) <= away
            problem += float(midpoint) - expression <= away
            slacks.append(away * (float(weight.nutrition) / scale))

    cost = pulp.lpSum(float(dish.cost_per_serving) * portions[dish.dish_id] for dish in usable)
    problem += cost <= float(constraints.budget)

    count = pulp.lpSum(pick.values())
    problem += count >= constraints.dish_count_min
    problem += count <= constraints.dish_count_max

    for category in DishCategory:
        same_category = pulp.lpSum(
            pick[dish.dish_id] for dish in usable if dish.category is category
        )
        minimum = constraints.category_min.get(category, 0)
        maximum = constraints.category_max.get(category)
        if minimum:
            problem += same_category >= minimum
        if maximum is not None:
            problem += same_category <= maximum

    for method in CookingMethod:
        same_method = pulp.lpSum(
            pick[dish.dish_id] for dish in usable if dish.cooking_method is method
        )
        problem += same_method <= float(constraints.max_method_ratio) * count

    # 食材种类数：y_i 表示「至少有一道选中的菜用到食材 i」，这是线性可表达的
    ingredient_ids = sorted({item for dish in usable for item in dish.ingredient_ids})
    used = {
        ingredient_id: pulp.LpVariable(f"y_{index}", cat="Binary")
        for index, ingredient_id in enumerate(ingredient_ids)
    }
    for dish in usable:
        for ingredient_id in dish.ingredient_ids:
            problem += used[ingredient_id] >= pick[dish.dish_id]
    if ingredient_ids:
        problem += pulp.lpSum(used.values()) >= constraints.min_ingredient_kinds

    max_popularity = max((float(dish.popularity) for dish in usable), default=1.0) or 1.0
    popularity = pulp.lpSum(
        float(dish.popularity) / max_popularity * pick[dish.dish_id] for dish in usable
    )
    problem += (
        pulp.lpSum(slacks)
        + float(weight.cost) * cost / float(constraints.budget)
        - float(weight.popularity) * popularity / max(constraints.dish_count_max, 1)
    )

    status = pulp.LpStatus[problem.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=time_limit))]
    if status != "Optimal":
        raise InfeasibleError(status, _diagnose(constraints, usable))

    chosen = [dish for dish in usable if (pick[dish.dish_id].value() or 0) > 0.5]
    portions_by_dish = {
        dish.dish_id: Decimal(str(round(portions[dish.dish_id].value() or 0, 2))) for dish in chosen
    }
    items = [
        PlannedDish(
            dish_id=dish.dish_id,
            name=dish.name,
            servings=portions_by_dish[dish.dish_id],
            cost=(dish.cost_per_serving * portions_by_dish[dish.dish_id]).quantize(Decimal("0.01")),
        )
        for dish in chosen
    ]
    totals = {
        target.code: _sum_field(target.code, chosen, portions_by_dish, diners)
        for target in constraints.targets
        if target.code in FIELD_BY_CODE
    }
    return PlanResult(
        items=items,
        per_capita=totals,
        cost=sum((item.cost for item in items), Decimal("0")).quantize(Decimal("0.01")),
        binding=_binding(constraints, totals),
        solver_status=status,
    )


def _scale_of(target: PlanTarget) -> Decimal:
    """把不同量纲的偏差折算到同一个尺度，否则权重之间没法比。"""
    if target.lower is not None and target.upper is not None:
        midpoint = (target.lower + target.upper) / 2
        return midpoint if midpoint > 0 else Decimal("1")
    bound = target.upper if target.upper is not None else target.lower
    return bound if bound and bound > 0 else Decimal("1")


def _midpoint(target: PlanTarget) -> Decimal | None:
    """只对双边区间取中点；单边上限（油盐糖）不该被「拉向中间」。"""
    if target.lower is None or target.upper is None:
        return None
    return (target.lower + target.upper) / 2


def _sum_field(
    code: str,
    chosen: list[CandidateDish],
    portions: dict[UUID, Decimal],
    diners: Decimal,
) -> Decimal:
    field_name = FIELD_BY_CODE.get(code)
    if field_name is None:
        return Decimal("0")
    total = sum(
        (Decimal(str(getattr(dish, field_name))) * portions[dish.dish_id] for dish in chosen),
        Decimal("0"),
    )
    return (total / diners).quantize(Decimal("0.001"))


def _binding(constraints: PlanConstraints, totals: dict[str, Decimal]) -> list[str]:
    notes: list[str] = []
    for target in constraints.targets:
        actual = totals.get(target.code)
        if actual is None:
            continue
        if target.upper is not None and target.upper * Decimal(
            "0.98"
        ) <= actual <= target.upper * Decimal("1.001"):
            notes.append(f"{target.label}已接近上限 {target.upper}{target.unit}")
        if target.lower is not None and target.lower * Decimal(
            "0.999"
        ) <= actual <= target.lower * Decimal("1.02"):
            notes.append(f"{target.label}在下限附近 {target.lower}{target.unit}，请结合差距核对")
    return notes


def _diagnose(constraints: PlanConstraints, usable: list[CandidateDish]) -> list[str]:
    reasons: list[str] = []
    cheapest = min((dish.cost_per_serving for dish in usable), default=Decimal("0"))
    if cheapest * constraints.dish_count_min > constraints.budget:
        reasons.append("预算连最低道数的菜都买不下来")
    available_kinds = {item for dish in usable for item in dish.ingredient_ids}
    if constraints.min_ingredient_kinds > len(available_kinds):
        reasons.append("候选菜品能提供的食材种类数达不到下限")
    if constraints.dish_count_max < constraints.dish_count_min:
        reasons.append("菜品数量上下限写反了")
    for target in constraints.targets:
        field_name = FIELD_BY_CODE.get(target.code)
        if field_name is None or target.upper is None:
            continue
        lowest = min(
            (Decimal(str(getattr(dish, field_name))) for dish in usable), default=Decimal("0")
        )
        if lowest > target.upper:
            reasons.append(f"任何一道菜的{target.label}都已超过上限 {target.upper}{target.unit}")
    return reasons or ["约束之间互相冲突，请放宽其中一项后重试"]

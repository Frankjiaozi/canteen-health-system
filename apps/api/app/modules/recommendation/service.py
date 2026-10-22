"""菜单推荐的业务逻辑。

把候选装配成求解器输入、调用纯函数、把结果**连同依据一起落库**，再读成对外结构。

落库的快照必须自包含：菜单、差距、理由、约束边界、目标口径全部存下来。
这样「上周那份建议当时说了什么」可以直接复核，而不是拿今天的参数重算一遍——
重算出来的数字和当初给人看的那份对不上，复盘就无从谈起。
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.logging import get_logger
from app.modules.nutrition import service as nutrition_service
from app.modules.recommendation import repository, solver, targets
from app.modules.recommendation.models import MenuSuggestion
from app.modules.recommendation.schemas import (
    DecideRequest,
    MenuPackageRead,
    MenuSuggestionRead,
    NutrientGap,
    PlannedDishRead,
    SuggestionReason,
    SuggestionSummary,
)
from app.shared.enums import (
    DishCategory,
    MealType,
    PackageCode,
    SeasoningCategory,
    SuggestionStatus,
)

logger = get_logger(__name__)

#: 一餐供应几道菜
DISH_COUNT_MIN = 4
DISH_COUNT_MAX = 6
#: 每道菜占就餐人次的份数区间。
#:
#: 这个区间不能放宽：取 0.5~1.5 时求解器会把好几道菜压在 0.5 那一端（「做 442 份给 885 人」），
#: 取 0.8~1.3 时米饭顶到上限、其余压到下限——两次都是数学上达标、食堂看着不像话。
#: 食堂的实际做法就是「每人一份」，变化只在于有人多要有人不要，所以取 0.9~1.1。
SERVING_RATIO_MIN = Decimal("0.9")
SERVING_RATIO_MAX = Decimal("1.1")
#: 单一烹饪方式的道数占比上限：炒菜不超过一半
MAX_METHOD_RATIO = Decimal("0.5")
#: 各类菜的道数上下限。一餐的基本结构：必有主食、汤与素菜，
#: 主食与汤各不超过两份，其余类别按荤素搭配留出余地。
CATEGORY_MIN: dict[DishCategory, int] = {
    DishCategory.STAPLE: 1,
    DishCategory.SOUP: 1,
    DishCategory.VEGETABLE: 1,
}
CATEGORY_MAX: dict[DishCategory, int] = {
    # 主食**每天只排一份**。菜品库里只有两种主食（米饭、馒头），
    # 允许一天排两份的话，第二天就没有主食可排了（「同一道菜不连续两日重复」把它们都排除了），
    # 结果是第二天直接「排不出来」。食堂本来就一天一种主食，限制它不损失什么。
    DishCategory.STAPLE: 1,
    DishCategory.SOUP: 1,
    DishCategory.MEAT: 2,
    DishCategory.HALF_MEAT: 2,
    DishCategory.VEGETABLE: 3,
}

_OIL = SeasoningCategory.EDIBLE_OIL
_SALT = SeasoningCategory.SALT
_SUGAR = SeasoningCategory.SUGAR

#: 判定达标时允许的相对零头。
#:
#: 求解器有内部容差，份数又取到两位小数，于是重算出来的实际值可能比边界低千分之一
#: （720 的能量算出来 719.999）。把它报成「低于目标」，看的人会以为约束没生效。
_BOUND_TOLERANCE = Decimal("0.001")


def generate(
    session: Session,
    *,
    on_date: date,
    meal_type: MealType = MealType.LUNCH,
    diner_count: int | None = None,
    servings_by_dish: dict[UUID, Decimal] | None = None,
    excluded_dish_ids: frozenset[UUID] = frozenset(),
    budget_per_person: Decimal | None = None,
    extra_excluded: Collection[UUID] | None = None,
    usage_counts: dict[UUID, int] | None = None,
) -> MenuSuggestionRead:
    """生成一份菜单建议。

    **份数不由推荐决定**。推荐回答的是「明天做哪几道菜」；份数是预测的活——
    它要考虑明天是不是放假、这道菜历史卖得怎么样，而推荐手里没有这些信息。

    营养评估固定按「每人一份」的标准套餐：每道入选菜贡献一个标准份。
    预测份数只用于采购与出餐计划，不进入套餐营养计算。
    """
    settings = get_settings()
    dishes = repository.load_active_dishes(session)
    materials = repository.load_materials(session)
    popularity = repository.load_popularity(session, on_date=on_date, meal_type=meal_type)
    standards = repository.load_standards(session)

    # 早餐与午晚餐是**两个互不相交的池子**。
    #
    # 早餐按固定组合供应（学校早饭就是每天那几样），不走推荐求解；勾了
    # 「早餐固定供应」的菜同时从午晚餐的池子里拿掉——否则同一道菜会在一天里
    # 出现两次，而这正是「三餐菜单算出一样」最难解释的一种表现。
    is_breakfast = meal_type is MealType.BREAKFAST
    pool = {
        dish_id: dish
        for dish_id, dish in dishes.items()
        if bool(dish.is_breakfast_staple) is is_breakfast
    }
    # 缺单价不在这里判：下面按**入选的那几道菜**重算（materials 是全量加载的）。
    # 没被选中的菜缺单价，不该让这份方案的成本背上「偏低」的警告。
    candidates, snapshots, _ = _candidates(
        session, dishes=pool, materials=materials, popularity=popularity
    )
    if not candidates:
        if is_breakfast:
            raise BusinessRuleError(
                "早餐还没有可用的菜：在菜品库里给早餐那几道菜勾上「早餐固定供应」，"
                "并确保它们有配方、上过菜单"
            )
        raise BusinessRuleError("没有可用于推荐的菜品：菜品需要有配方，并且至少供应过一次")

    plan_targets, target_basis = targets.build_targets(meal_type, standards)
    diners = diner_count or repository.load_latest_diner_count(
        session, on_date=on_date, meal_type=meal_type
    )
    baseline = servings_by_dish or {candidate.dish_id: Decimal(diners) for candidate in candidates}
    # 三类排除各有各的来源，分开留着，理由里才说得清是**哪条规则**排掉的
    if is_breakfast:
        # 早餐是固定组合：不套「昨天不重复」「同日不重样」这两条结构规则，
        # 否则「每天固定」就不成立了。但**用户明确要求排除的菜仍然照办**——
        # 显式指令优先于默认组合。
        previous: set[UUID] = set()
        other_meal: set[UUID] = set()
    else:
        # 库里前一天供应过的菜要排除；批量排菜单时，前一天的那份菜单可能还在内存里
        # 没落库（是同一批生成出来的），所以允许把「上一批算出来的菜」一并传进来，
        # 否则「不连续两日重复」在批量里会形同虚设
        previous = repository.load_previous_dishes(session, on_date=on_date, meal_type=meal_type)
        # 同一天的另一餐已经排上的菜也不再出现。**主食除外**：主食池里只有米饭与
        # 馒头两道，一天两餐都排除的话候选择不出菜单，而中午晚上都上米饭本来就是
        # 食堂的常态——要的是「菜不重样」，不是「连米饭都不能一样」。
        other_meal = {
            dish_id
            for dish_id in repository.load_other_meal_dishes(
                session, on_date=on_date, meal_type=meal_type
            )
            if getattr(dishes.get(dish_id), "category", None) is not DishCategory.STAPLE
        }
    batch_excluded = set(extra_excluded or ())
    requested_excluded = set(excluded_dish_ids)
    excluded = previous | other_meal | batch_excluded | requested_excluded

    per_person = (
        budget_per_person
        if budget_per_person is not None
        else Decimal(str(settings.nutrition_meal_budget_per_person))
    )
    budget = (per_person * diners).quantize(Decimal("0.01"))
    constraints = solver.PlanConstraints(
        targets=plan_targets,
        budget=budget,
        diner_count=diners,
        dish_count_min=DISH_COUNT_MIN,
        dish_count_max=DISH_COUNT_MAX,
        serving_ratio_min=SERVING_RATIO_MIN,
        serving_ratio_max=SERVING_RATIO_MAX,
        max_method_ratio=MAX_METHOD_RATIO,
        min_ingredient_kinds=targets.min_ingredient_kinds(standards),
        category_min=CATEGORY_MIN,
        category_max=CATEGORY_MAX,
        fixed_servings=baseline,
        excluded_dish_ids=frozenset(excluded),
        usage_counts=usage_counts or {},
        standard_package=True,
    )

    try:
        package_plans = (
            _breakfast_package_plans(candidates, constraints)
            if is_breakfast
            else solver.solve_package_pair(candidates, constraints)
        )
    except solver.InfeasibleError as error:
        raise BusinessRuleError(str(error), details={"conflicts": error.conflicts}) from error

    shares = {
        PackageCode.A: Decimal(str(settings.package_share_a)),
        PackageCode.B: Decimal(str(settings.package_share_b)),
    }
    all_items = [
        item for code in (PackageCode.A, PackageCode.B) for item in package_plans[code].items
    ]
    missing_price = any(materials[item.dish_id].missing_price for item in all_items)
    by_id = {dish.dish_id: dish for dish in candidates}
    package_rows: list[MenuPackageRead] = []
    package_details: dict[str, dict[str, object]] = {}
    package_codes_by_dish: dict[UUID, list[PackageCode]] = {}
    for code in (PackageCode.A, PackageCode.B):
        plan = package_plans[code]
        gaps = _gaps(plan_targets, plan.per_capita, meal_type)
        reasons = _reasons(
            plan,
            gaps,
            by_id,
            previous,
            other_meal,
            dishes,
            breakfast=is_breakfast,
        )
        if code is PackageCode.B:
            prior_package_names = "、".join(
                sorted(
                    by_id[item.dish_id].name
                    for item in package_plans[PackageCode.A].items
                    if by_id[item.dish_id].category is not DishCategory.STAPLE
                )
            )
            if prior_package_names:
                reasons.append(
                    SuggestionReason(
                        kind="constraint",
                        text=f"套餐 A 已安排 {prior_package_names}，套餐 B 不再重复（主食可共用）",
                    )
                )
        package_cost = (plan.cost * shares[code]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        dish_rows = [
            PlannedDishRead(
                dish_id=str(item.dish_id),
                dish_name=by_id[item.dish_id].name,
                package_codes=[code],
                package_labels=[code.label],
                category_label=by_id[item.dish_id].category.label,
                cooking_method_label=by_id[item.dish_id].cooking_method.label,
                cost=str(item.cost),
                energy_kcal=str(by_id[item.dish_id].energy_kcal),
                salt_g=str(by_id[item.dish_id].salt_g),
                popularity=str(by_id[item.dish_id].popularity.quantize(Decimal("1"))),
                nutrition_basis=snapshots[item.dish_id],
            )
            for item in plan.items
        ]
        package_rows.append(
            MenuPackageRead(
                code=code,
                label=code.label,
                dishes=dish_rows,
                gaps=gaps,
                reasons=reasons,
                cost_estimate=str(package_cost),
                budget=str(budget),
                per_capita={key: str(value) for key, value in plan.per_capita.items()},
                binding=plan.binding,
                solver_status=plan.solver_status,
            )
        )
        package_details[code.value] = {
            "per_capita": {key: str(value) for key, value in plan.per_capita.items()},
            "items": [row.model_dump(mode="json") for row in gaps],
            "reasons": [row.model_dump(mode="json") for row in reasons],
            "binding": plan.binding,
            "solver_status": plan.solver_status,
            "cost_estimate": str(package_cost),
        }
        for item in plan.items:
            package_codes_by_dish.setdefault(item.dish_id, []).append(code)

    common_staples = {
        dish_id
        for dish_id, codes in package_codes_by_dish.items()
        if len(codes) == 2 and by_id[dish_id].category is DishCategory.STAPLE
    }
    flat_items = []
    seen_dish_ids: set[UUID] = set()
    for code in (PackageCode.A, PackageCode.B):
        for item in package_plans[code].items:
            if item.dish_id not in seen_dish_ids:
                flat_items.append(item)
                seen_dish_ids.add(item.dish_id)

    def dish_package_codes(dish_id: UUID) -> list[PackageCode]:
        if dish_id in common_staples:
            return [PackageCode.COMMON]
        return package_codes_by_dish[dish_id]

    flat_gaps = package_rows[0].gaps
    reasons = _unique_reasons([reason for package in package_rows for reason in package.reasons])
    if batch_excluded:
        names = "、".join(
            sorted(str(getattr(dishes.get(item), "name", item)) for item in batch_excluded)
        )
        reasons.append(SuggestionReason(kind="constraint", text=f"按批量前一日计划排除：{names}"))
    if requested_excluded:
        names = "、".join(
            sorted(str(getattr(dishes.get(item), "name", item)) for item in requested_excluded)
        )
        reasons.append(SuggestionReason(kind="constraint", text=f"按本次要求排除：{names}"))

    candidate_menu: list[dict[str, object]] = []
    for item in flat_items:
        codes = dish_package_codes(item.dish_id)
        allocated_share = sum(
            (shares[code] for code in codes if code is not PackageCode.COMMON),
            Decimal("0"),
        )
        if PackageCode.COMMON in codes:
            allocated_share = Decimal("1")
        candidate_menu.append(
            {
                "dish_id": str(item.dish_id),
                "dish_name": by_id[item.dish_id].name,
                "package_codes": [code.value for code in codes],
                "package_labels": [code.label for code in codes],
                "category_label": by_id[item.dish_id].category.label,
                "cooking_method_label": by_id[item.dish_id].cooking_method.label,
                "cost": str(
                    (by_id[item.dish_id].cost_per_serving * diners * allocated_share).quantize(
                        Decimal("0.01")
                    )
                ),
                "energy_kcal": str(by_id[item.dish_id].energy_kcal),
                "salt_g": str(by_id[item.dish_id].salt_g),
                "popularity": str(by_id[item.dish_id].popularity.quantize(Decimal("1"))),
                "nutrition_basis": snapshots[item.dish_id],
                # 套餐营养固定记录一个标准份；采购份数在 menu-plan 链路单独分配。
                "planned_servings": "1",
            }
        )
    total_cost = sum(
        (package_plans[code].cost * shares[code] for code in shares), Decimal("0")
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    suggestion = repository.save_suggestion(
        session,
        on_date=on_date,
        meal_type=meal_type,
        candidate_menu=candidate_menu,
        nutrition_gap={
            "diner_count": diners,
            "per_capita": package_rows[0].per_capita,
            "items": [row.model_dump(mode="json") for row in flat_gaps],
            "budget": str(budget),
            "package_basis": "TWO_STANDARD_PACKAGES_WITH_DISJOINT_NON_STAPLES",
            "package_shares": {
                PackageCode.A.value: str(shares[PackageCode.A]),
                PackageCode.B.value: str(shares[PackageCode.B]),
            },
            "packages": package_details,
            "target_basis": target_basis,
            "binding": package_rows[0].binding,
            "solver_status": package_rows[0].solver_status,
            "excluded_dishes": sorted(
                str(getattr(dishes.get(dish_id), "name", dish_id)) for dish_id in excluded
            ),
            "missing_price_warning": (
                "部分食材或调味料没有单价，成本因此偏低——要拿它做预算判断，先把单价补齐"
                if missing_price
                else None
            ),
        },
        cost_estimate=total_cost,
        reasons=[reason.model_dump(mode="json") for reason in reasons],
    )
    session.commit()
    logger.info(
        "菜单推荐：%s %s，%d 道菜，成本 %s 元（%d 人次）",
        on_date,
        meal_type.label,
        len(flat_items),
        total_cost,
        diners,
    )
    return read_suggestion(suggestion)


def candidate_dish_ids(
    session: Session, *, on_date: date | None = None, meal_type: MealType | None = None
) -> list[UUID]:
    """可作为推荐候选的菜品。

    「合并页」要先拿这份清单去预测份数、再交给推荐选菜，两边的候选集必须是同一批，
    否则会出现「预测了但没参与推荐」或「推荐了却没有份数」的错位。

    早餐与午晚餐的池子互不相交（见 `generate` 里的说明），所以这里必须按餐次取，
    不能用「全部菜品」——那会让午晚餐预测一批根本不会入选的早餐菜。
    """
    dishes = repository.load_active_dishes(session)
    materials = repository.load_materials(session)
    popularity = repository.load_popularity(session, on_date=on_date, meal_type=meal_type)
    want_breakfast = meal_type is MealType.BREAKFAST
    return [
        dish_id
        for dish_id, usage in materials.items()
        if usage.ingredient_ids
        and dish_id in dishes
        and dish_id in popularity
        and bool(dishes[dish_id].is_breakfast_staple) is want_breakfast
    ]


def latest_suggestion_id(session: Session, *, on_date: date, meal_type: MealType) -> UUID | None:
    """这一天这一餐最近生成的那一版菜单，没有就返回空。

    「一键导入当日菜单」按日期区间干活，调用方只给区间、不给一串 id——
    那样刷新页面或换个人来点，结果都一样。
    """
    for row in repository.list_suggestions(session, on_date=on_date, limit=20):
        if row.meal_type is meal_type:
            return row.id
    return None


def latest_diner_count(
    session: Session, *, on_date: date, meal_type: MealType = MealType.LUNCH
) -> int:
    """最近一次采集里的就餐人次。

    别的域（例如「明日菜单与采购」）要按人次折算人均供给时走这里问，
    而不是自己去读推荐域的表。
    """
    return repository.load_latest_diner_count(session, on_date=on_date, meal_type=meal_type)


def reopen_suggestion(session: Session, *, suggestion_id: UUID) -> MenuSuggestionRead:
    """把一版推荐改回「待确认」。

    只给「撤回同步」用：菜单已经退回原样了，推荐记录却还写着「已采纳」的话，
    两处状态就对不上——而这种对不上最难查。
    """
    suggestion = repository.get_suggestion(session, suggestion_id)
    if suggestion is None:
        raise NotFoundError("推荐不存在")
    suggestion.status = SuggestionStatus.PENDING
    suggestion.rejected_reason = None
    suggestion.decided_by = None
    suggestion.decided_at = None
    session.commit()
    return read_suggestion(suggestion)


@dataclass(frozen=True, slots=True)
class PlannedDish:
    """一版菜单里的一道菜：做哪道 + 计划做多少份。"""

    dish_id: UUID
    planned_servings: Decimal | None
    package_codes: tuple[PackageCode, ...] = (PackageCode.COMMON,)


def planned_dishes(
    session: Session, *, suggestion_id: UUID, on_date: date, meal_type: MealType
) -> tuple[list[PlannedDish], SuggestionStatus]:
    """读出某一版菜单的菜品与计划份数，供「同步到当日数据」落库。

    读的是**快照**而不是重新算一遍：同步要落的是人当时看到并确认的那一版，
    重算会算出可能不一样的结果，那就不是「同步」而是「悄悄换一份菜单」了。
    """
    suggestion = repository.get_suggestion(session, suggestion_id)
    if suggestion is None:
        raise NotFoundError("推荐不存在")
    if suggestion.date != on_date or suggestion.meal_type is not meal_type:
        raise BusinessRuleError(
            f"这一版菜单是 {suggestion.date} {suggestion.meal_type.label} 的，"
            f"与要同步的 {on_date} {meal_type.label} 对不上"
        )
    rows = [
        PlannedDish(
            dish_id=UUID(str(row["dish_id"])),
            planned_servings=(
                None
                if row.get("planned_servings") is None
                else Decimal(str(row["planned_servings"]))
            ),
            package_codes=tuple(
                PackageCode(str(code))
                for code in row.get(
                    "package_codes",
                    [PackageCode.COMMON.value],
                )
            ),
        )
        for row in (suggestion.candidate_menu or [])
    ]
    if not rows:
        raise BusinessRuleError("这一版菜单里没有菜品，无法同步")
    return rows, suggestion.status


def _breakfast_package_plans(
    candidates: list[solver.CandidateDish],
    constraints: solver.PlanConstraints,
) -> dict[PackageCode, solver.PlanResult]:
    """把固定早餐组合稳定地分成 A/B 两份。

    主食同时进入两份套餐，并在采购侧记为共用；其余菜按类别与数量均衡拆分。
    早餐不求解营养目标，但仍沿用标准套餐的营养核算与差距展示。
    """
    # 固定组合也必须遵守用户的显式排除；fixed_plan 本身只核算，不筛选候选。
    candidates = [dish for dish in candidates if dish.dish_id not in constraints.excluded_dish_ids]
    common = [dish for dish in candidates if dish.category is DishCategory.STAPLE]
    others = [dish for dish in candidates if dish.category is not DishCategory.STAPLE]
    grouped: dict[DishCategory, list[solver.CandidateDish]] = {
        category: [] for category in DishCategory
    }
    for dish in others:
        grouped[dish.category].append(dish)

    packages: dict[PackageCode, list[solver.CandidateDish]] = {
        PackageCode.A: list(common),
        PackageCode.B: list(common),
    }
    for category in DishCategory:
        for dish in sorted(grouped[category], key=lambda row: (row.name, str(row.dish_id))):
            count_a = sum(
                1
                for item in packages[PackageCode.A]
                if item.category is category and item.category is not DishCategory.STAPLE
            )
            count_b = sum(
                1
                for item in packages[PackageCode.B]
                if item.category is category and item.category is not DishCategory.STAPLE
            )
            target = (
                PackageCode.A
                if (count_a, len(packages[PackageCode.A]))
                <= (count_b, len(packages[PackageCode.B]))
                else PackageCode.B
            )
            packages[target].append(dish)

    if not packages[PackageCode.A] or not packages[PackageCode.B]:
        raise solver.InfeasibleError(
            "早餐无法组成两份套餐",
            ["早餐固定供应菜不足；请至少保留一道主食和两道非主食菜"],
        )
    return {
        code: solver.fixed_plan(dishes, constraints=constraints)
        for code, dishes in packages.items()
    }


def _unique_reasons(reasons: list[SuggestionReason]) -> list[SuggestionReason]:
    seen: set[tuple[str, str]] = set()
    rows: list[SuggestionReason] = []
    for reason in reasons:
        key = (reason.kind, reason.text)
        if key in seen:
            continue
        seen.add(key)
        rows.append(reason)
    return rows


def _candidates(
    session: Session,
    *,
    dishes: Mapping[UUID, Any],
    materials: dict[UUID, repository.MaterialUsage],
    popularity: dict[UUID, tuple[Decimal, int]],
) -> tuple[list[solver.CandidateDish], dict[UUID, str], bool]:
    """筛出真正的候选，并记下每道菜的营养取自哪一层。

    三样缺一不可：菜在用、有配方、有历史记录。没有配方算不出营养；
    没有历史说明这道菜从没做过（可能刚建好还没排过菜单），把它推荐出去没有依据。
    """
    usable_ids = [
        dish_id
        for dish_id, usage in materials.items()
        if usage.ingredient_ids and dish_id in dishes and dish_id in popularity
    ]
    snapshots = nutrition_service.latest_per_serving_snapshots(session, usable_ids)
    candidates: list[solver.CandidateDish] = []
    basis: dict[UUID, str] = {}
    missing_price = False
    for dish_id in usable_ids:
        dish = dishes[dish_id]
        usage = materials[dish_id]
        snapshot = snapshots[dish_id]
        missing_price = missing_price or usage.missing_price
        basis[dish_id] = snapshot.value_type_label
        candidates.append(
            solver.CandidateDish(
                dish_id=dish_id,
                name=dish.name,
                category=dish.category,
                cooking_method=dish.cooking_method,
                energy_kcal=snapshot.energy_kcal,
                protein_g=snapshot.protein_g,
                fat_g=snapshot.fat_g,
                carb_g=snapshot.carb_g,
                sodium_mg=snapshot.sodium_mg,
                oil_g=usage.seasoning_g.get(_OIL, Decimal("0")),
                salt_g=usage.seasoning_g.get(_SALT, Decimal("0")),
                sugar_g=usage.seasoning_g.get(_SUGAR, Decimal("0")),
                cost_per_serving=usage.cost_per_serving,
                popularity=popularity[dish_id][0],
                ingredient_ids=frozenset(usage.ingredient_ids),
            )
        )
    return candidates, basis, missing_price


def _gaps(
    plan_targets: tuple[solver.PlanTarget, ...], per_capita: dict[str, Decimal], meal_type: MealType
) -> list[NutrientGap]:
    """差距分析。

    油盐糖的上限在约束里用的是**每日基准**（见 targets.py 的说明），但那样报出来一律是
    「达标」，等于没做差距分析。所以这几项的差距改为对照**按餐次折算的推荐量**：
    午餐的盐该 ≤2 克，实际 4.2 克——这才是食堂能拿去改的数字。
    """
    share = targets.meal_share(meal_type)
    rows: list[NutrientGap] = []
    for target in plan_targets:
        actual = per_capita.get(target.code, Decimal("0"))
        is_seasoning = target.code in {"EDIBLE_OIL", "SALT", "ADDED_SUGAR"}
        reported_upper = (
            (target.upper * share).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if is_seasoning and target.upper is not None
            else target.upper
        )
        status = "ok"
        gap = Decimal("0")
        if reported_upper is not None and actual > reported_upper * (1 + _BOUND_TOLERANCE):
            status, gap = "over", actual - reported_upper
        elif target.lower is not None and actual < target.lower * (1 - _BOUND_TOLERANCE):
            status, gap = "under", target.lower - actual
        note = None
        if is_seasoning and target.upper is not None:
            note = (
                f"目标按每日基准 {target.upper}{target.unit} 折到这一餐（占 {share * 100:.0f}%）；"
                f"求解时的上限用的是每日基准本身，否则现有配方下必然无解"
            )
        rows.append(
            NutrientGap(
                code=target.code,
                label=target.label,
                unit=target.unit,
                target_text=(
                    f"≤ {reported_upper}{target.unit}"
                    if is_seasoning and reported_upper is not None
                    else _target_text(target)
                ),
                actual=str(actual),
                status=status,
                gap=str(gap.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
                note=note,
            )
        )
    return rows


def _target_text(target: solver.PlanTarget) -> str:
    if target.lower is not None and target.upper is not None:
        return f"{target.lower} ~ {target.upper}{target.unit}"
    if target.upper is not None:
        return f"≤ {target.upper}{target.unit}"
    return f"≥ {target.lower}{target.unit}"


def _reasons(
    plan: solver.PlanResult,
    gaps: list[NutrientGap],
    by_id: dict[UUID, solver.CandidateDish],
    previous: set[UUID],
    other_meal: set[UUID],
    dishes: Mapping[UUID, Any],
    *,
    breakfast: bool = False,
) -> list[SuggestionReason]:
    """把求解结果讲成人能看的话。

    每条都对着一个**可核对的事实**：某个指标的缺口、某个贴边的约束、受欢迎度排名。
    「营养均衡」这种话对厨师长没有任何意义，写不出事实的理由不如不写。
    """
    reasons: list[SuggestionReason] = []
    if breakfast:
        reasons.append(
            SuggestionReason(
                kind="constraint",
                text=(
                    "早餐按固定组合供应，不参与每日选菜——"
                    "要改菜单就在菜品库里调整「早餐固定供应」那几道菜"
                ),
            )
        )
    for row in gaps:
        if row.status == "under":
            reasons.append(
                SuggestionReason(
                    kind="nutrition",
                    text=f"{row.label}还差 {row.gap}{row.unit} 才到目标区间（{row.target_text}）",
                )
            )
        elif row.status == "over":
            reasons.append(
                SuggestionReason(
                    kind="nutrition",
                    text=f"{row.label}超出目标 {row.gap}{row.unit}（目标 {row.target_text}）",
                )
            )
    for note in plan.binding:
        reasons.append(SuggestionReason(kind="constraint", text=note))

    ranked = sorted(plan.items, key=lambda item: by_id[item.dish_id].popularity, reverse=True)
    for index, item in enumerate(ranked[:2], start=1):
        dish = by_id[item.dish_id]
        reasons.append(
            SuggestionReason(
                kind="popularity",
                text=(
                    f"{dish.name}在历史供应里平均出餐 {dish.popularity.quantize(Decimal('1'))} 份，"
                    f"入选菜里排第 {index}"
                ),
            )
        )
    methods = {by_id[item.dish_id].cooking_method.label for item in plan.items}
    if len(methods) > 1:
        reasons.append(
            SuggestionReason(
                kind="variety",
                text=f"这一餐覆盖 {len(methods)} 种烹饪方式（{'、'.join(sorted(methods))}）",
            )
        )
    if previous:
        names = "、".join(
            sorted(str(getattr(dishes.get(dish_id), "name", dish_id)) for dish_id in previous)
        )
        reasons.append(
            SuggestionReason(
                kind="constraint",
                text=f"按「同一道菜不连续两日重复」，昨天这一餐供应的 {names} 本次不参与",
            )
        )
    if other_meal:
        names = "、".join(
            sorted(str(getattr(dishes.get(dish_id), "name", dish_id)) for dish_id in other_meal)
        )
        reasons.append(
            SuggestionReason(
                kind="constraint",
                text=f"同一天的另一餐已经有 {names}，本次不再重复（主食可以重样）",
            )
        )
    return reasons


def read_suggestion(suggestion: MenuSuggestion) -> MenuSuggestionRead:
    """把落库的推荐读成对外结构。不重算，只用当初存下来的快照。"""
    menu = suggestion.candidate_menu or []
    gap_data = suggestion.nutrition_gap or {}

    def dish_read(row: Mapping[str, Any]) -> PlannedDishRead:
        codes = [
            PackageCode(str(value))
            for value in row.get("package_codes", [PackageCode.COMMON.value])
        ]
        return PlannedDishRead(
            dish_id=str(row.get("dish_id")),
            dish_name=str(row.get("dish_name")),
            package_codes=codes,
            package_labels=[code.label for code in codes],
            category_label=str(row.get("category_label", "")),
            cooking_method_label=str(row.get("cooking_method_label", "")),
            cost=str(row.get("cost")),
            energy_kcal=str(row.get("energy_kcal", "—")),
            salt_g=str(row.get("salt_g", "—")),
            popularity=str(row.get("popularity", "—")),
            nutrition_basis=str(row.get("nutrition_basis", "")),
        )

    flat_dishes = [dish_read(row) for row in menu]
    package_data = gap_data.get("packages", {})
    packages: list[MenuPackageRead] = []
    for code in (PackageCode.A, PackageCode.B):
        detail = package_data.get(code.value)
        if not isinstance(detail, dict):
            continue
        packages.append(
            MenuPackageRead(
                code=code,
                label=code.label,
                dishes=[
                    dish
                    for dish in flat_dishes
                    if code in dish.package_codes or PackageCode.COMMON in dish.package_codes
                ],
                gaps=[NutrientGap(**row) for row in detail.get("items", [])],
                reasons=[SuggestionReason(**row) for row in detail.get("reasons", [])],
                cost_estimate=str(detail.get("cost_estimate", "0")),
                budget=str(gap_data.get("budget", "")),
                per_capita={
                    str(key): str(value)
                    for key, value in dict(detail.get("per_capita", {})).items()
                },
                binding=list(detail.get("binding", [])),
                solver_status=str(detail.get("solver_status", "")),
            )
        )

    return MenuSuggestionRead(
        id=str(suggestion.id),
        date=suggestion.date,
        meal_type=suggestion.meal_type,
        meal_type_label=suggestion.meal_type.label,
        status=suggestion.status,
        status_label=suggestion.status.label,
        dishes=flat_dishes,
        packages=packages,
        package_shares={
            str(key): str(value) for key, value in dict(gap_data.get("package_shares", {})).items()
        },
        gaps=[NutrientGap(**row) for row in gap_data.get("items", [])],
        reasons=[SuggestionReason(**row) for row in (suggestion.reasons or [])],
        cost_estimate=str(suggestion.cost_estimate or 0),
        budget=str(gap_data.get("budget", "")),
        diner_count=int(gap_data.get("diner_count", 0)),
        target_basis=dict(gap_data.get("target_basis", {})),
        binding=list(gap_data.get("binding", [])),
        solver_status=str(gap_data.get("solver_status", "")),
        excluded_dishes=list(gap_data.get("excluded_dishes", [])),
        missing_price_warning=gap_data.get("missing_price_warning"),
        rejected_reason=suggestion.rejected_reason,
        decided_at=suggestion.decided_at,
    )


def list_suggestions(
    session: Session, *, on_date: date | None, limit: int
) -> list[SuggestionSummary]:
    return [
        SuggestionSummary(
            id=str(row.id),
            date=row.date,
            meal_type=row.meal_type,
            meal_type_label=row.meal_type.label,
            status=row.status,
            status_label=row.status.label,
            dish_count=len(row.candidate_menu or []),
            cost_estimate=str(row.cost_estimate or 0),
            created_at=row.created_at,
            rejected_reason=row.rejected_reason,
        )
        for row in repository.list_suggestions(session, on_date=on_date, limit=limit)
    ]


def get_suggestion(session: Session, suggestion_id: UUID) -> MenuSuggestionRead:
    suggestion = repository.get_suggestion(session, suggestion_id)
    if suggestion is None:
        raise NotFoundError("推荐不存在")
    return read_suggestion(suggestion)


def decide(
    session: Session, *, suggestion_id: UUID, payload: DecideRequest, actor_id: UUID | None
) -> MenuSuggestionRead:
    """采纳或否决。否决必须写明原因——需求里写明它用于后续迭代。"""
    suggestion = session.scalar(
        select(MenuSuggestion).where(MenuSuggestion.id == suggestion_id).with_for_update()
    )
    if suggestion is None:
        raise NotFoundError("推荐不存在")
    if payload.status is SuggestionStatus.PENDING:
        raise BusinessRuleError("只能采纳或否决，不能改回待确认")
    if (suggestion.nutrition_gap or {}).get("publication"):
        raise ConflictError("这份方案已确认发布，请通过新方案调整菜单，不能改写确认记录")
    if payload.status is SuggestionStatus.REJECTED and not (payload.reason or "").strip():
        raise BusinessRuleError("否决必须写明原因，它会被用来改进后续推荐")
    suggestion.status = payload.status
    suggestion.rejected_reason = payload.reason
    suggestion.decided_by = actor_id
    suggestion.decided_at = datetime.now(get_settings().timezone)
    session.commit()
    return read_suggestion(suggestion)

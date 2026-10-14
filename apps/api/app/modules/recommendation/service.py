"""菜单推荐的业务逻辑。

把候选装配成求解器输入、调用纯函数、把结果**连同依据一起落库**，再读成对外结构。

落库的快照必须自包含：菜单、差距、理由、约束边界、目标口径全部存下来。
这样「上周那份建议当时说了什么」可以直接复核，而不是拿今天的参数重算一遍——
重算出来的数字和当初给人看的那份对不上，复盘就无从谈起。
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import BusinessRuleError, NotFoundError
from app.core.logging import get_logger
from app.modules.nutrition import service as nutrition_service
from app.modules.recommendation import repository, solver, targets
from app.modules.recommendation.models import MenuSuggestion
from app.modules.recommendation.schemas import (
    DecideRequest,
    MenuSuggestionRead,
    NutrientGap,
    PlannedDishRead,
    SuggestionReason,
    SuggestionSummary,
)
from app.shared.enums import DishCategory, MealType, SeasoningCategory, SuggestionStatus

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
    DishCategory.STAPLE: 2,
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
) -> MenuSuggestionRead:
    """生成一份菜单建议。

    **份数不由推荐决定**。推荐回答的是「明天做哪几道菜」；份数是预测的活——
    它要考虑明天是不是放假、这道菜历史卖得怎么样，而推荐手里没有这些信息。

    但份数必须参与营养评估：「人均供给」= Σ(单份营养 × 份数) ÷ 人次，
    不知道做多少份就算不出这一餐提供了多少营养。所以它是**输入**，不是推荐的结果。
    不传时按「每人一份」估——那只是评估基准，不代表建议这么做。
    """
    settings = get_settings()
    dishes = repository.load_active_dishes(session)
    materials = repository.load_materials(session)
    popularity = repository.load_popularity(session)
    standards = repository.load_standards(session)

    candidates, snapshots, missing_price = _candidates(
        session, dishes=dishes, materials=materials, popularity=popularity
    )
    if not candidates:
        raise BusinessRuleError("没有可用于推荐的菜品：菜品需要有配方，并且至少供应过一次")

    plan_targets, target_basis = targets.build_targets(meal_type, standards)
    diners = diner_count or repository.load_latest_diner_count(session, on_date=on_date)
    baseline = servings_by_dish or {candidate.dish_id: Decimal(diners) for candidate in candidates}
    excluded = repository.load_previous_dishes(session, on_date=on_date, meal_type=meal_type)
    budget = (Decimal(str(settings.nutrition_meal_budget_per_person)) * diners).quantize(
        Decimal("0.01")
    )
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
    )

    plan = solver.solve_menu(candidates, constraints)
    by_id = {dish.dish_id: dish for dish in candidates}
    gaps = _gaps(plan_targets, plan.per_capita, meal_type)
    reasons = _reasons(plan, gaps, by_id, excluded, dishes)

    suggestion = repository.save_suggestion(
        session,
        on_date=on_date,
        meal_type=meal_type,
        candidate_menu=[
            {
                "dish_id": str(item.dish_id),
                "dish_name": by_id[item.dish_id].name,
                "category_label": by_id[item.dish_id].category.label,
                "cooking_method_label": by_id[item.dish_id].cooking_method.label,
                "cost": str(item.cost),
                "energy_kcal": str(by_id[item.dish_id].energy_kcal),
                "salt_g": str(by_id[item.dish_id].salt_g),
                "popularity": str(by_id[item.dish_id].popularity.quantize(Decimal("1"))),
                "nutrition_basis": snapshots[item.dish_id],
            }
            for item in plan.items
        ],
        nutrition_gap={
            "diner_count": diners,
            "per_capita": {code: str(value) for code, value in plan.per_capita.items()},
            "items": [row.model_dump(mode="json") for row in gaps],
            "budget": str(budget),
            "target_basis": target_basis,
            "binding": plan.binding,
            "solver_status": plan.solver_status,
            "excluded_dishes": sorted(
                str(getattr(dishes.get(dish_id), "name", dish_id)) for dish_id in excluded
            ),
            "missing_price_warning": (
                "部分食材或调味料没有单价，成本因此偏低——要拿它做预算判断，先把单价补齐"
                if missing_price
                else None
            ),
        },
        cost_estimate=plan.cost,
        reasons=[reason.model_dump(mode="json") for reason in reasons],
    )
    session.commit()
    logger.info(
        "菜单推荐：%s %s，%d 道菜，成本 %s 元（%d 人次）",
        on_date,
        meal_type.label,
        len(plan.items),
        plan.cost,
        diners,
    )
    return read_suggestion(suggestion)


def candidate_dish_ids(session: Session) -> list[UUID]:
    """可作为推荐候选的菜品。

    「合并页」要先拿这份清单去预测份数、再交给推荐选菜，两边的候选集必须是同一批，
    否则会出现「预测了但没参与推荐」或「推荐了却没有份数」的错位。
    """
    dishes = repository.load_active_dishes(session)
    materials = repository.load_materials(session)
    popularity = repository.load_popularity(session)
    return [
        dish_id
        for dish_id, usage in materials.items()
        if usage.ingredient_ids and dish_id in dishes and dish_id in popularity
    ]


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
                cost_per_serving=usage.cost_per_serving.quantize(Decimal("0.01")),
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
    excluded: set[UUID],
    dishes: Mapping[UUID, Any],
) -> list[SuggestionReason]:
    """把求解结果讲成人能看的话。

    每条都对着一个**可核对的事实**：某个指标的缺口、某个贴边的约束、受欢迎度排名。
    「营养均衡」这种话对厨师长没有任何意义，写不出事实的理由不如不写。
    """
    reasons: list[SuggestionReason] = []
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
    if excluded:
        names = "、".join(
            sorted(str(getattr(dishes.get(dish_id), "name", dish_id)) for dish_id in excluded)
        )
        reasons.append(
            SuggestionReason(
                kind="constraint",
                text=f"按「同一道菜不连续两日重复」，昨天供应的 {names} 本次不参与",
            )
        )
    return reasons


def read_suggestion(suggestion: MenuSuggestion) -> MenuSuggestionRead:
    """把落库的推荐读成对外结构。不重算，只用当初存下来的快照。"""
    menu = suggestion.candidate_menu or []
    gap_data = suggestion.nutrition_gap or {}
    return MenuSuggestionRead(
        id=str(suggestion.id),
        date=suggestion.date,
        meal_type=suggestion.meal_type,
        meal_type_label=suggestion.meal_type.label,
        status=suggestion.status,
        status_label=suggestion.status.label,
        dishes=[
            PlannedDishRead(
                dish_id=str(row.get("dish_id")),
                dish_name=str(row.get("dish_name")),
                category_label=str(row.get("category_label", "")),
                cooking_method_label=str(row.get("cooking_method_label", "")),
                cost=str(row.get("cost")),
                energy_kcal=str(row.get("energy_kcal", "—")),
                salt_g=str(row.get("salt_g", "—")),
                popularity=str(row.get("popularity", "—")),
                nutrition_basis=str(row.get("nutrition_basis", "")),
            )
            for row in menu
        ],
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
    suggestion = repository.get_suggestion(session, suggestion_id)
    if suggestion is None:
        raise NotFoundError("推荐不存在")
    if payload.status is SuggestionStatus.PENDING:
        raise BusinessRuleError("只能采纳或否决，不能改回待确认")
    if payload.status is SuggestionStatus.REJECTED and not (payload.reason or "").strip():
        raise BusinessRuleError("否决必须写明原因，它会被用来改进后续推荐")
    suggestion.status = payload.status
    suggestion.rejected_reason = payload.reason
    suggestion.decided_by = actor_id
    suggestion.decided_at = datetime.now(get_settings().timezone)
    session.commit()
    return read_suggestion(suggestion)

"""「明日菜单与采购」——把推荐、预测、采购串成一件事（纯编排，不自己造数）。

三者的分工是这次改动的核心，写在这里省得以后翻代码去猜：

| 环节 | 谁做 | 输出 |
| --- | --- | --- |
| 做哪几道菜 | 推荐（整数规划） | 菜品集 + 营养差距 + 理由 |
| 各做多少份 | **预测**（同星期历史 × 日历修正） | 每道菜的份数 |
| 买多少料 | 由两者相乘得到 | 各食材/调味料的公斤数与金额 |

**份数由预测给，不由推荐算**：份数要看明天是不是放假、这道菜历史卖得怎么样，
推荐手里没有这些信息。营养按每人一份标准套餐评估，预测份数只用于采购与出餐计划。

「同步至当日数据」是这条链路的最后一环（`sync_to_day`）：把这一版菜单写进那一天的**菜单日**，
每日采集的「当日供应菜品」因此一打开就是勾好的，公开大屏当天早上也能直接显示。
采集页提交时按实际供应整份覆盖——一天供应了哪些菜，始终只有 `menu_days` 这一份数据。
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from app.core.config import get_settings
from app.core.errors import AppError, BusinessRuleError, ConflictError
from app.core.logging import get_logger
from app.modules.auth import repository as auth_repository
from app.modules.auth.service import to_auth_user
from app.modules.collection import service as collection_service
from app.modules.forecast import service as forecast_service
from app.modules.forecast.schemas import IngredientRequirement
from app.modules.menuplan import publication
from app.modules.menuplan.schemas import (
    DailyMenuPlanResponse,
    MenuPlanBatchDay,
    MenuPlanBatchResult,
    MenuPlanDish,
    MenuPlanPackage,
    MenuPlanResponse,
    MenuPlanSyncResult,
    PublishPlanRequest,
)
from app.modules.recommendation import repository as recommendation_repository
from app.modules.recommendation import service as recommendation_service
from app.shared.enums import MealType, PackageCode, SuggestionStatus
from sqlalchemy.orm import Session

logger = get_logger(__name__)

#: 预测不出来时的基准份数怎么取：按每人一份估。
#: 这不是「建议做这么多」，只是在拿不到预测时保证采购量还能算出来，并在页面上标出来。
FALLBACK_SERVINGS_PER_DINER = Decimal("1")

#: 一次批量最多排多少天。上限不是性能问题，是**人**的问题：一次生成一学期，
#: 出了错要一条条翻，也没人会在生成之后逐天核对。两到四周是能一次看完、看完还能改的量。
BATCH_MAX_DAYS = 31

#: 平均每人的预测份数超过这个数，就认为「人次」与「份数」量级对不上。
#: 正常一天里，各菜的份数大致是就餐人次的一半上下（米饭接近一，汤菜更低），
#: 平均到 1.0 以上意味着多数菜都要做出比就餐人数还多的份数——那不是菜单问题，是数据问题。
SERVINGS_PER_DINER_LIMIT = Decimal("1")


@dataclass
class _PurchaseTotal:
    unit: str
    quantity: Decimal = Decimal("0")
    unit_price: str | None = None
    estimated_cost: Decimal = Decimal("0")
    priced: bool = False


def _date_range(start: date, end: date) -> list[date]:
    if end < start:
        raise BusinessRuleError("结束日期不能早于开始日期")
    days = (end - start).days + 1
    if days > BATCH_MAX_DAYS:
        raise BusinessRuleError(f"一次最多排 {BATCH_MAX_DAYS} 天，这次选了 {days} 天；请分成几次排")
    return [start + timedelta(days=offset) for offset in range(days)]


def servings_mismatch_note(servings: Collection[Decimal], *, diners: int) -> str | None:
    """人次与预测份数量级对不上时，给一句话。

    份数是按历史算的，人次取最近一次采集。两者量级差太多时（例如人次 180、份数 300~900），
    人均油盐糖会被成倍放大，**任何**菜单都超上限——求解器只会说「约束互相冲突」，
    看的人完全不知道问题出在人次上。这一条把它翻译成人能照做的话。

    只在**排不出来之后**用它补充说明，不拿它当门槛：量级偏大但仍然排得出来的情况是有的
    （求解器可以挑低盐的菜），事先拦住会把能用的菜单也挡掉。
    """
    values = [value for value in servings if value > 0]
    if not values or diners <= 0:
        return None
    average = sum(values, Decimal("0")) / Decimal(len(values)) / diners
    if average <= SERVINGS_PER_DINER_LIMIT:
        return None
    return (
        f"另外，这一餐的预测份数与就餐人次量级对不上：最近一次采集只有 {diners} 人次，"
        f"而各道菜的预测份数在 {min(values).quantize(Decimal('1'))}~"
        f"{max(values).quantize(Decimal('1'))} 份之间（平均是人次的 {average:.1f} 倍）。"
        "按这个人次折算人均油盐糖会被成倍放大，请先到「每日采集」核对最近几次采集的人次。"
    )


def build_menu_plan(
    session: Session,
    *,
    on_date: date,
    meal_type: MealType = MealType.LUNCH,
    diner_count: int | None = None,
    excluded_dish_ids: frozenset[UUID] = frozenset(),
    budget_per_person: Decimal | None = None,
    extra_excluded: Collection[UUID] | None = None,
    usage_counts: dict[UUID, int] | None = None,
) -> MenuPlanResponse:
    """生成明天的菜单与采购建议。"""
    settings = get_settings()
    candidate_ids = recommendation_service.candidate_dish_ids(
        session, on_date=on_date, meal_type=meal_type
    )
    unknown = excluded_dish_ids - set(recommendation_repository.load_active_dishes(session))
    if unknown:
        raise BusinessRuleError("排除列表包含不存在或已停用的菜品，请刷新菜品后重试")
    if not candidate_ids:
        if meal_type is MealType.BREAKFAST:
            raise BusinessRuleError(
                "早餐还没有可用的菜：在菜品库里给早餐那几道菜勾上「早餐固定供应」，"
                "并确保它们有配方、上过菜单"
            )
        raise BusinessRuleError("没有可用于推荐的菜品：菜品需要有配方，并且至少供应过一次")
    catalog_before = publication.catalog_tokens(session, candidate_ids)

    diner_prediction = forecast_service.predict_diner_count(
        session, on_date=on_date, meal_type=meal_type
    )
    diners = diner_count or diner_prediction.predicted_diner_count
    if diners is None:
        raise BusinessRuleError(
            "无法预测就餐人次：同餐次历史不足，请在任务条件中填写预计人次后再生成"
        )

    # 先预测：逐菜独立，所以不必先知道菜单就能算出每道菜的份数
    prediction = forecast_service.predict_dishes(
        session, on_date=on_date, meal_type=meal_type, dish_ids=candidate_ids
    )
    fallback_servings = Decimal(diners) * FALLBACK_SERVINGS_PER_DINER
    servings_by_dish = {
        dish_id: prediction.servings.get(dish_id, fallback_servings) for dish_id in candidate_ids
    }
    scale_note = ""
    if diner_count is not None and prediction.servings:
        historical_diners = (
            diner_prediction.predicted_diner_count
            or recommendation_repository.load_latest_diner_count(
                session, on_date=on_date, meal_type=meal_type
            )
        )
        if historical_diners:
            scale = Decimal(diner_count) / Decimal(historical_diners)
            servings_by_dish = {
                dish_id: (quantity * scale).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                if dish_id in prediction.servings
                else quantity
                for dish_id, quantity in servings_by_dish.items()
            }
            scale_note = (
                f"情景份数 = 历史预测 × 指定人次 {diner_count} / 系统预计人次 "
                f"{historical_diners}；等比例调整是假设，不是新增实测。"
            )
        else:
            scale_note = "历史人数不足，无法按指定人次等比例换算份数；当前保留历史预测份数。"

    # 再推荐：拿预测份数当营养评估基准，只回答「做哪几道菜」
    try:
        suggestion = recommendation_service.generate(
            session,
            on_date=on_date,
            meal_type=meal_type,
            diner_count=diners,
            servings_by_dish=servings_by_dish,
            excluded_dish_ids=excluded_dish_ids,
            budget_per_person=budget_per_person,
            extra_excluded=extra_excluded,
            usage_counts=usage_counts,
        )
    except BusinessRuleError as error:
        note = servings_mismatch_note(servings_by_dish.values(), diners=diners)
        raise BusinessRuleError(
            f"{error.message}。{note}" if note else error.message, details=error.details
        ) from error

    recommended_ids = [UUID(dish.dish_id) for dish in suggestion.dishes]
    forecast_service.persist_predictions(
        session,
        prediction,
        on_date=on_date,
        meal_type=meal_type,
        only=frozenset(recommended_ids),
    )
    session.commit()

    package_shares = {
        PackageCode.A: Decimal(
            suggestion.package_shares.get(PackageCode.A.value, settings.package_share_a)
        ),
        PackageCode.B: Decimal(
            suggestion.package_shares.get(PackageCode.B.value, settings.package_share_b)
        ),
    }

    def allocated_servings(dish: Any) -> Decimal:
        dish_id = UUID(str(dish.dish_id))
        total = servings_by_dish[dish_id]
        codes = list(getattr(dish, "package_codes", [PackageCode.COMMON]))
        if not codes or PackageCode.COMMON in codes:
            return total
        share = sum(
            (package_shares[code] for code in codes if code in package_shares),
            Decimal("0"),
        )
        return (total * share).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    dishes = [
        MenuPlanDish(
            dish_id=dish.dish_id,
            dish_name=dish.dish_name,
            package_codes=list(dish.package_codes),
            package_labels=list(dish.package_labels),
            is_shared=PackageCode.COMMON in dish.package_codes,
            category_label=dish.category_label,
            cooking_method_label=dish.cooking_method_label,
            energy_kcal=dish.energy_kcal,
            salt_g=dish.salt_g,
            popularity=dish.popularity,
            nutrition_basis=dish.nutrition_basis,
            predicted_servings=(
                None
                if UUID(dish.dish_id) not in prediction.servings
                else str(servings_by_dish[UUID(dish.dish_id)])
            ),
            predicted_basis_label=next(
                (row.basis_label for row in prediction.dishes if row.dish_id == UUID(dish.dish_id)),
                None,
            ),
            prediction_fallback=UUID(dish.dish_id) not in prediction.servings,
            planned_servings=str(allocated_servings(dish)),
        )
        for dish in suggestion.dishes
    ]
    purchase_servings = {
        UUID(dish.dish_id): Decimal(dish.planned_servings or "0") for dish in dishes
    }
    requirements, total_cost = forecast_service.build_purchase_list(
        session,
        servings_by_dish=purchase_servings,
    )
    packages = [
        MenuPlanPackage(
            code=package.code,
            label=package.label,
            dish_ids=[
                dish.dish_id
                for dish in dishes
                if package.code in dish.package_codes or dish.is_shared
            ],
            gaps=package.gaps,
            reasons=package.reasons,
            cost_estimate=package.cost_estimate,
            per_capita=package.per_capita,
        )
        for package in suggestion.packages
    ]

    fallback_names = [dish.dish_name for dish in dishes if dish.prediction_fallback]
    if meal_type is MealType.BREAKFAST:
        notes = [
            "早餐按固定组合供应：上哪几道菜由菜品库的「早餐固定供应」决定，不参与每日选菜。",
            "早餐主食由 A/B 两份套餐共用；其它菜不重复，采购按配置的套餐占比分摊。",
        ]
    else:
        notes = [
            "菜品由推荐在营养目标下选出；份数由预测按同星期历史与日历修正给出。",
            "每餐生成 A/B 两份每人套餐；非主食不重复，主食允许共用。",
            "营养按每份套餐独立评估；预测份数只用于采购，不再反过来改变套餐营养。",
            "同一天的另一餐已经排过的菜不会再选（主食可以重样）。",
        ]
    if diner_count is None:
        interval = (
            f"，参考区间 {diner_prediction.lower}–{diner_prediction.upper} 人"
            if diner_prediction.lower is not None and diner_prediction.upper is not None
            else ""
        )
        notes.append(
            f"就餐人次使用系统预计：{diners} 人（{diner_prediction.basis_label}{interval}）；"
            "可在任务条件中修改后重新计算。"
        )
    if fallback_names:
        notes.append(
            "这几道菜历史不足、预测不出份数，采购量按「每人一份」估算：" + "、".join(fallback_names)
        )
    if scale_note:
        notes.append(scale_note)
    logger.info(
        "菜单与采购：%s %s，%d 道菜，采购 %d 项，%s 元",
        on_date,
        meal_type.label,
        len(dishes),
        len(requirements),
        total_cost,
    )
    result = MenuPlanResponse(
        date=on_date,
        meal_type=meal_type,
        meal_type_label=meal_type.label,
        diner_count=diners,
        suggestion_id=suggestion.id,
        dishes=dishes,
        packages=packages,
        package_shares={
            PackageCode.A.value: str(package_shares[PackageCode.A]),
            PackageCode.B.value: str(package_shares[PackageCode.B]),
        },
        gaps=suggestion.gaps,
        reasons=suggestion.reasons,
        requirements=requirements,
        total_cost=total_cost,
        budget=suggestion.budget,
        target_basis=suggestion.target_basis,
        missing_price_warning=suggestion.missing_price_warning,
        excluded_dishes=suggestion.excluded_dishes,
        calendar_notes=[prediction.calendar_note] if prediction.calendar_note else [],
        skipped_predictions=prediction.skipped,
        servings_note=(
            f"采购量按 A/B 占比 {package_shares[PackageCode.A]:.0%}/"
            f"{package_shares[PackageCode.B]:.0%} 分摊：非主食只计入所属套餐，"
            "共用主食只计一次；预测份数来自逐菜预测，预测不出来时"
            "退回「每人一份」估算并逐行标注。"
        ),
        notes=notes,
        budget_per_person=str(Decimal(suggestion.budget) / Decimal(diners)),
        requested_excluded_dish_ids=sorted(str(item) for item in excluded_dish_ids),
        calculation_version=publication.CALCULATION_VERSION,
    )
    # 保存完整计算快照；发布和导出使用这份快照，不能拿今天的数据重算旧方案。
    return publication.save_snapshot(session, result, catalog_before)


def build_daily_plan(
    session: Session,
    *,
    on_date: date,
    budget_per_person: Decimal | None = None,
    excluded_dish_ids: frozenset[UUID] = frozenset(),
) -> DailyMenuPlanResponse:
    """一次排出早、午、晚三餐，并把采购单合并成一张。

    顺序是早餐 → 午餐 → 晚餐：早餐固定组合；午餐先选；晚餐读取同一天已生成的午餐，
    避开它的非主食菜。每餐仍使用自己的系统预测人次与份数预测，不把三餐硬凑成同一个规模。
    """
    meals: list[MenuPlanResponse] = []
    used_counts: dict[UUID, int] = {}
    previous_lunch: tuple[UUID, ...] = ()
    for meal_type in (MealType.BREAKFAST, MealType.LUNCH, MealType.DINNER):
        plan = build_menu_plan(
            session,
            on_date=on_date,
            meal_type=meal_type,
            budget_per_person=budget_per_person,
            excluded_dish_ids=excluded_dish_ids,
            # 早餐与午晚池子互不相交；晚餐把刚生成的午餐带进排除集。
            extra_excluded=previous_lunch if meal_type is MealType.DINNER else None,
            usage_counts=used_counts,
        )
        meals.append(plan)
        previous_lunch = (
            tuple(UUID(dish.dish_id) for dish in plan.dishes) if meal_type is MealType.LUNCH else ()
        )
        for dish in plan.dishes:
            dish_id = UUID(dish.dish_id)
            used_counts[dish_id] = used_counts.get(dish_id, 0) + 1

    requirements, total_cost = aggregate_requirements(meals)
    budget = sum((Decimal(meal.budget) for meal in meals), Decimal("0")).quantize(Decimal("0.01"))
    fallback = [
        dish.dish_name for meal in meals for dish in meal.dishes if dish.prediction_fallback
    ]
    notes = [
        "一键生成早、午、晚三餐：早餐固定组合；午餐先排，晚餐避开午餐已选的非主食菜。",
        "三餐各自使用系统预测的就餐人次与份数；采购单已把相同食材和调味料合并。",
        "同步时按餐次分别校验：已录采集的那一餐跳过，其余餐次继续写入当日数据。",
    ]
    if fallback:
        notes.append("部分菜历史不足，份数按「每人一份」估算：" + "、".join(fallback))
    result = DailyMenuPlanResponse(
        date=on_date,
        meals=meals,
        requirements=requirements,
        total_cost=total_cost,
        budget=str(budget),
        servings_note=(
            "采购量 = 三餐各自推荐菜 × 该菜预测份数；相同食材/调味料合并后按公斤报量，"
            "按金额从大到小排。"
        ),
        fallback_dishes=fallback,
        notes=notes,
        suggestion_ids={meal.meal_type.value: meal.suggestion_id for meal in meals},
        calculation_version=publication.CALCULATION_VERSION,
    )
    logger.info(
        "三餐菜单：%s，%d 餐，合并采购 %d 项，%s 元",
        on_date,
        len(meals),
        len(requirements),
        total_cost,
    )
    return result


def aggregate_requirements(
    meals: Collection[MenuPlanResponse],
) -> tuple[list[IngredientRequirement], str | None]:
    """把各餐采购项按名称合并；金额只用有单价的项相加。"""
    totals: dict[str, _PurchaseTotal] = {}
    for meal in meals:
        for row in meal.requirements:
            entry = totals.setdefault(row.name, _PurchaseTotal(unit=row.unit))
            entry.quantity += Decimal(row.quantity)
            if row.unit_price is not None:
                entry.unit_price = row.unit_price
            if row.estimated_cost is not None:
                entry.estimated_cost += Decimal(row.estimated_cost)
                entry.priced = True

    rows: list[IngredientRequirement] = []
    total_cost = Decimal("0")
    any_priced = False
    for name, entry in totals.items():
        quantity = entry.quantity.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        cost = (
            entry.estimated_cost.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if entry.priced
            else None
        )
        if cost is not None:
            total_cost += cost
            any_priced = True
        rows.append(
            IngredientRequirement(
                name=name,
                unit=entry.unit,
                quantity=str(quantity),
                unit_price=None if entry.unit_price is None else str(entry.unit_price),
                estimated_cost=None if cost is None else str(cost),
            )
        )
    rows.sort(
        key=lambda row: (
            row.estimated_cost is None,
            -Decimal(row.estimated_cost or "0"),
            row.name,
        )
    )
    return rows, str(total_cost.quantize(Decimal("0.01"))) if any_priced else None


def sync_to_day(
    session: Session,
    *,
    on_date: date,
    meal_type: MealType,
    suggestion_id: UUID,
    actor_id: UUID | None = None,
    commit: bool = True,
) -> MenuPlanSyncResult:
    _ensure_day_is_free(session, on_date=on_date, meal_type=meal_type)
    result = _sync_one(
        session,
        on_date=on_date,
        meal_type=meal_type,
        suggestion_id=suggestion_id,
        actor_id=actor_id,
        commit=commit,
    )
    return result


def _ensure_day_is_free(session: Session, *, on_date: date, meal_type: MealType) -> None:
    if collection_service.has_collection(session, on_date=on_date, meal_type=meal_type):
        raise BusinessRuleError(
            f"{on_date} {meal_type.label} 已经录过采集了，菜单以实际供应为准；"
            "要调整请到「每日采集」里改，不要把计划盖上去"
        )


def _sync_one(
    session: Session,
    *,
    on_date: date,
    meal_type: MealType,
    suggestion_id: UUID,
    actor_id: UUID | None = None,
    commit: bool = True,
) -> MenuPlanSyncResult:
    """兼容旧同步入口，统一使用完整快照、目录核验、餐次锁和发布回执。"""
    _planned, status = recommendation_service.planned_dishes(
        session, suggestion_id=suggestion_id, on_date=on_date, meal_type=meal_type
    )
    if status is SuggestionStatus.REJECTED:
        raise BusinessRuleError("这一版菜单已被否决，不能同步；请重新生成一版")
    suggestion = recommendation_repository.get_suggestion(session, suggestion_id)
    snapshot = (suggestion.nutrition_gap or {}).get("menu_plan_snapshot") if suggestion else None
    if not snapshot:
        raise ConflictError("旧建议没有完整快照，请重新生成并确认后同步")
    user = auth_repository.get_by_id(session, actor_id) if actor_id else None
    if user is None or not user.is_active:
        raise BusinessRuleError("同步菜单需要有效的当前账号")
    plan = MenuPlanResponse.model_validate(snapshot["plan"])
    receipt = publication.publish(
        session,
        suggestion_id=suggestion_id,
        payload=PublishPlanRequest(
            snapshot_token=plan.snapshot_token, expected_menu_token=plan.expected_menu_token
        ),
        actor=to_auth_user(user),
        commit=commit,
    )
    return MenuPlanSyncResult(
        date=on_date,
        meal_type=meal_type,
        meal_type_label=meal_type.label,
        suggestion_id=str(suggestion_id),
        dish_count=receipt.dish_count,
        nutrition_rows=receipt.dish_count,
        planned_servings_filled=sum(1 for row in plan.dishes if row.planned_servings is not None),
        message=f"已写入 {on_date} {meal_type.label}的当日数据：{receipt.dish_count} 道菜。每日采集按计划勾好，公开大屏可查看；实际采集仍需如实录入。",
    )


def generate_batch(
    session: Session,
    *,
    start_date: date,
    end_date: date,
    meal_type: MealType = MealType.LUNCH,
) -> MenuPlanBatchResult:
    """按日期区间一次排一段菜单。

    逐日顺序生成，并**把上一天算出来的菜带进下一天的排除集**：
    「同一道菜不连续两日重复」这条约束，在批量里靠库里的菜单日是接不上的——
    这一批的菜单还没落库（要等「一键导入」）。不带的话，批量排出来的菜单
    会出现连着两天同一道菜，而那正是这条约束要防的。

    已经录过采集的日子直接跳过：那一天菜单以实际供应为准，排了也用不上。
    """
    dates = _date_range(start_date, end_date)
    rows: list[MenuPlanBatchDay] = []
    previous_ids: Collection[UUID] = ()
    previous_date: date | None = None
    used_times: dict[UUID, int] = {}

    for day in dates:
        if collection_service.has_collection(session, on_date=day, meal_type=meal_type):
            rows.append(
                MenuPlanBatchDay(
                    date=day,
                    status="SKIPPED",
                    status_label="已跳过",
                    reason="这一天已经录过采集了，菜单以实际供应为准",
                )
            )
            previous_ids, previous_date = (), None
            continue

        extra = previous_ids if previous_date == day - timedelta(days=1) else ()
        try:
            plan = build_menu_plan(
                session,
                on_date=day,
                meal_type=meal_type,
                extra_excluded=extra,
                usage_counts=used_times,
            )
        except BusinessRuleError as error:
            # 单独一天排不出来不该拖垮整段：把原因记在这一行上，其余日子继续。
            # 这也是批量排菜单的意义——先把能排的排出来，剩下的看原因再调。
            session.rollback()
            rows.append(
                MenuPlanBatchDay(
                    date=day,
                    status="FAILED",
                    status_label="排不出来",
                    reason=str(error),
                )
            )
            previous_ids, previous_date = (), None
            continue

        cost_per_person = (
            None
            if plan.total_cost is None or plan.diner_count <= 0
            else str((Decimal(plan.total_cost) / plan.diner_count).quantize(Decimal("0.01")))
        )
        rows.append(
            MenuPlanBatchDay(
                date=day,
                status="GENERATED",
                status_label="已生成",
                suggestion_id=plan.suggestion_id,
                dish_names=[dish.dish_name for dish in plan.dishes],
                dish_count=len(plan.dishes),
                diner_count=plan.diner_count,
                total_cost=plan.total_cost,
                cost_per_person=cost_per_person,
                requirements_count=len(plan.requirements),
                calendar_note=plan.calendar_notes[0] if plan.calendar_notes else None,
            )
        )
        previous_ids = tuple(UUID(dish.dish_id) for dish in plan.dishes)
        previous_date = day
        for dish in plan.dishes:
            dish_id = UUID(dish.dish_id)
            used_times[dish_id] = used_times.get(dish_id, 0) + 1

    generated = sum(1 for row in rows if row.status == "GENERATED")
    skipped = sum(1 for row in rows if row.status == "SKIPPED")
    failed = sum(1 for row in rows if row.status == "FAILED")
    logger.info(
        "批量排菜单：%s ~ %s %s，生成 %d 天，跳过 %d 天，失败 %d 天",
        start_date,
        end_date,
        meal_type.label,
        generated,
        skipped,
        failed,
    )
    return MenuPlanBatchResult(
        start_date=start_date,
        end_date=end_date,
        meal_type=meal_type,
        meal_type_label=meal_type.label,
        days=len(rows),
        generated=generated,
        skipped=skipped,
        failed=failed,
        rows=rows,
        message=(
            f"{len(rows)} 天里排出 {generated} 天"
            + (f"，跳过 {skipped} 天" if skipped else "")
            + (f"，{failed} 天排不出来" if failed else "")
            + "。确认无误后点「一键导入当日菜单」，把这批菜单写进各天的当日数据。"
        ),
    )


def sync_batch(
    session: Session,
    *,
    start_date: date,
    end_date: date,
    meal_type: MealType = MealType.LUNCH,
    actor_id: UUID | None = None,
) -> MenuPlanBatchResult:
    """把区间内每一天**最近生成的那一版菜单**写进当日数据。

    按区间而不是按一串 id：调用方只要说「这几天」，刷新页面、换个人来点，
    结果都一样。哪一天没有生成过、哪一天已经录过采集，都会在那一天上说明。
    """
    dates = _date_range(start_date, end_date)
    rows: list[MenuPlanBatchDay] = []

    for day in dates:
        suggestion_id = recommendation_service.latest_suggestion_id(
            session, on_date=day, meal_type=meal_type
        )
        if suggestion_id is None:
            rows.append(
                MenuPlanBatchDay(
                    date=day,
                    status="SKIPPED",
                    status_label="已跳过",
                    reason="这一天还没有生成过菜单",
                )
            )
            continue
        try:
            _ensure_day_is_free(session, on_date=day, meal_type=meal_type)
            result = _sync_one(
                session,
                on_date=day,
                meal_type=meal_type,
                suggestion_id=suggestion_id,
                actor_id=actor_id,
            )
        except AppError as error:
            # 一天导入失败不该影响其余各天：把原因写在这一行上，接着导入下一天
            session.rollback()
            rows.append(
                MenuPlanBatchDay(
                    date=day,
                    status="FAILED",
                    status_label="导入失败",
                    suggestion_id=str(suggestion_id),
                    reason=str(error),
                )
            )
            continue

        rows.append(
            MenuPlanBatchDay(
                date=day,
                status="IMPORTED",
                status_label="已导入",
                suggestion_id=str(suggestion_id),
                dish_count=result.dish_count,
                nutrition_rows=result.nutrition_rows,
            )
        )

    imported = sum(1 for row in rows if row.status == "IMPORTED")
    skipped = sum(1 for row in rows if row.status == "SKIPPED")
    failed = sum(1 for row in rows if row.status == "FAILED")
    logger.info(
        "批量导入当日菜单：%s ~ %s %s，导入 %d 天，跳过 %d 天，失败 %d 天",
        start_date,
        end_date,
        meal_type.label,
        imported,
        skipped,
        failed,
    )
    return MenuPlanBatchResult(
        start_date=start_date,
        end_date=end_date,
        meal_type=meal_type,
        meal_type_label=meal_type.label,
        days=len(rows),
        imported=imported,
        skipped=skipped,
        failed=failed,
        rows=rows,
        message=(
            f"{len(rows)} 天里导入 {imported} 天"
            + (f"，跳过 {skipped} 天" if skipped else "")
            + (f"，{failed} 天失败" if failed else "")
            + "。这些天的每日采集已经按菜单勾好，公开大屏也看得到了。"
        ),
    )

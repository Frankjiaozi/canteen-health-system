"""「明日菜单与采购」——把推荐、预测、采购串成一件事（纯编排，不自己造数）。

三者的分工是这次改动的核心，写在这里省得以后翻代码去猜：

| 环节 | 谁做 | 输出 |
| --- | --- | --- |
| 做哪几道菜 | 推荐（整数规划） | 菜品集 + 营养差距 + 理由 |
| 各做多少份 | **预测**（同星期历史 × 日历修正） | 每道菜的份数 |
| 买多少料 | 由两者相乘得到 | 各食材/调味料的公斤数与金额 |

**份数由预测给，不由推荐算**：份数要看明天是不是放假、这道菜历史卖得怎么样，
推荐手里没有这些信息。但份数又必须参与营养评估（人均供给 = Σ单份营养 × 份数 ÷ 人次），
所以它是推荐的**输入**而不是输出。

「同步至当日数据」是这条链路的最后一环（`sync_to_day`）：把这一版菜单写进那一天的**菜单日**，
每日采集的「当日供应菜品」因此一打开就是勾好的，公开大屏当天早上也能直接显示。
采集页提交时按实际供应整份覆盖——一天供应了哪些菜，始终只有 `menu_days` 这一份数据。
"""

from __future__ import annotations

from collections.abc import Collection
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from app.core.errors import AppError, BusinessRuleError
from app.core.logging import get_logger
from app.modules.collection import service as collection_service
from app.modules.forecast import service as forecast_service
from app.modules.menu import service as menu_service
from app.modules.menuplan.schemas import (
    MenuPlanBatchDay,
    MenuPlanBatchResult,
    MenuPlanDish,
    MenuPlanResponse,
    MenuPlanSyncResult,
)
from app.modules.nutrition import service as nutrition_service
from app.modules.recommendation import service as recommendation_service
from app.modules.recommendation.schemas import DecideRequest
from app.shared.enums import MealType, SuggestionStatus
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
    extra_excluded: Collection[UUID] | None = None,
    usage_counts: dict[UUID, int] | None = None,
) -> MenuPlanResponse:
    """生成明天的菜单与采购建议。"""
    candidate_ids = recommendation_service.candidate_dish_ids(session)
    if not candidate_ids:
        raise BusinessRuleError("没有可用于推荐的菜品：菜品需要有配方，并且至少供应过一次")

    diners = diner_count or recommendation_service.latest_diner_count(session, on_date=on_date)

    # 先预测：逐菜独立，所以不必先知道菜单就能算出每道菜的份数
    prediction = forecast_service.predict_dishes(
        session, on_date=on_date, meal_type=meal_type, dish_ids=candidate_ids
    )
    fallback_servings = Decimal(diners) * FALLBACK_SERVINGS_PER_DINER
    servings_by_dish = {
        dish_id: prediction.servings.get(dish_id, fallback_servings) for dish_id in candidate_ids
    }

    # 再推荐：拿预测份数当营养评估基准，只回答「做哪几道菜」
    try:
        suggestion = recommendation_service.generate(
            session,
            on_date=on_date,
            meal_type=meal_type,
            diner_count=diners,
            servings_by_dish=servings_by_dish,
            extra_excluded=extra_excluded,
            usage_counts=usage_counts,
        )
    except BusinessRuleError as error:
        # 排不出来时，如果人次与份数量级差得离谱，把这件事一并说出来：
        # 那多半不是菜单的问题，而是最近一次采集的人次填错了
        note = servings_mismatch_note(prediction.servings.values(), diners=diners)
        raise BusinessRuleError(f"{error.message}。{note}" if note else error.message) from error

    recommended_ids = [UUID(dish.dish_id) for dish in suggestion.dishes]
    forecast_service.persist_predictions(
        session,
        prediction,
        on_date=on_date,
        meal_type=meal_type,
        only=frozenset(recommended_ids),
    )
    session.commit()

    requirements, total_cost = forecast_service.build_purchase_list(
        session,
        servings_by_dish={dish_id: servings_by_dish[dish_id] for dish_id in recommended_ids},
    )

    dishes = [
        MenuPlanDish(
            dish_id=dish.dish_id,
            dish_name=dish.dish_name,
            category_label=dish.category_label,
            cooking_method_label=dish.cooking_method_label,
            energy_kcal=dish.energy_kcal,
            salt_g=dish.salt_g,
            popularity=dish.popularity,
            nutrition_basis=dish.nutrition_basis,
            predicted_servings=(
                None
                if UUID(dish.dish_id) not in prediction.servings
                else str(prediction.servings[UUID(dish.dish_id)])
            ),
            predicted_basis_label=next(
                (row.basis_label for row in prediction.dishes if row.dish_id == UUID(dish.dish_id)),
                None,
            ),
            prediction_fallback=UUID(dish.dish_id) not in prediction.servings,
        )
        for dish in suggestion.dishes
    ]

    fallback_names = [dish.dish_name for dish in dishes if dish.prediction_fallback]
    notes = [
        "菜品由推荐在营养目标下选出；份数由预测按同星期历史与日历修正给出。",
        "推荐用预测份数评估营养，因此页面上只有一套份数。",
    ]
    if fallback_names:
        notes.append(
            "这几道菜历史不足、预测不出份数，采购量按「每人一份」估算：" + "、".join(fallback_names)
        )
    logger.info(
        "菜单与采购：%s %s，%d 道菜，采购 %d 项，%s 元",
        on_date,
        meal_type.label,
        len(dishes),
        len(requirements),
        total_cost,
    )
    return MenuPlanResponse(
        date=on_date,
        meal_type=meal_type,
        meal_type_label=meal_type.label,
        diner_count=diners,
        suggestion_id=suggestion.id,
        dishes=dishes,
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
            "采购量 = 推荐选出的菜 × 该菜明天的预测份数；"
            "预测不出来时退回「每人一份」估算并逐行标注。"
        ),
        notes=notes,
    )


def sync_to_day(
    session: Session,
    *,
    on_date: date,
    meal_type: MealType,
    suggestion_id: UUID,
    actor_id: UUID | None = None,
) -> MenuPlanSyncResult:
    _ensure_day_is_free(session, on_date=on_date, meal_type=meal_type)
    result = _sync_one(
        session,
        on_date=on_date,
        meal_type=meal_type,
        suggestion_id=suggestion_id,
        actor_id=actor_id,
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
) -> MenuPlanSyncResult:
    """把这一版菜单同步到那一天的当日数据：写菜单日 + 算营养 + 记下「已采纳」。

    做完这三件事，第二天会发生什么就确定了：

    - **每日采集**的「当日供应菜品」一打开就是勾好的（整份菜品库都列着，随时能改）；
    - **公开大屏**当天早上就有内容——它读菜单日与营养结果，两者在这里都齐了；
      而油盐糖、食物种类那类对照数据来自采集记录，采集之前如实显示「暂无」。

    为什么读快照而不是重算：同步要落的是**人当时看到并确认的那一版**。
    重算会算出可能不一样的结果，那就不是同步，是悄悄换一份菜单。

    「这一天有没有录过采集」由调用方先查（单日与批量各查一次，错误信息要带上下文）。
    """
    planned, status = recommendation_service.planned_dishes(
        session, suggestion_id=suggestion_id, on_date=on_date, meal_type=meal_type
    )
    if status is SuggestionStatus.REJECTED:
        raise BusinessRuleError("这一版菜单已被否决，不能同步；请重新生成一版")

    menu_service.plan_menu_day(
        session,
        on_date=on_date,
        meal_type=meal_type,
        dishes=[
            menu_service.PlannedDish(dish_id=row.dish_id, planned_servings=row.planned_servings)
            for row in planned
        ],
        created_by=actor_id,
    )
    # 大屏只展示有营养结果的菜，所以写菜单日与算营养必须一起做：
    # 只写菜单日的话，第二天早上大屏还是空的
    report = nutrition_service.compute_menu_day(session, on_date=on_date, meal_type=meal_type)

    # 同步即采纳：把「这一版被采用了」记下来，历史里查得到是谁在哪天定的菜单
    if status is SuggestionStatus.PENDING:
        recommendation_service.decide(
            session,
            suggestion_id=suggestion_id,
            payload=DecideRequest(status=SuggestionStatus.ACCEPTED, reason=None),
            actor_id=actor_id,
        )
    else:
        session.commit()

    filled = sum(1 for row in planned if row.planned_servings is not None)
    logger.info(
        "菜单已同步至当日数据：%s %s，%d 道菜，营养结果 %d 条",
        on_date,
        meal_type.label,
        len(planned),
        report.rows,
    )
    return MenuPlanSyncResult(
        date=on_date,
        meal_type=meal_type,
        meal_type_label=meal_type.label,
        suggestion_id=str(suggestion_id),
        dish_count=len(planned),
        nutrition_rows=report.rows,
        planned_servings_filled=filled,
        message=(
            f"已写入 {on_date} {meal_type.label}的当日数据：{len(planned)} 道菜，"
            f"{report.rows} 条营养结果。每日采集的供应菜品已按这份菜单勾好，"
            "公开大屏也看得到了；提交采集时会按实际供应覆盖。"
        ),
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

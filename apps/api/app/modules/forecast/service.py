"""消耗量预测的业务逻辑。

把历史装配成算法输入、调用纯函数、落库，并给出采购建议单。
算法本身在 `strategy.py`，这里不出现任何统计计算。
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.modules.forecast import repository, strategy
from app.modules.forecast.models import Holiday
from app.modules.forecast.schemas import (
    BacktestPoint,
    BacktestResult,
    DishForecast,
    ForecastRunResult,
    ForecastSample,
    HolidayPage,
    HolidayRead,
    HolidayWrite,
    IngredientRequirement,
)
from app.shared.enums import AnomalyFlag, HolidayKind, MealType

logger = get_logger(__name__)

#: 回测的达标线，取自需求文档的验收标准
TARGET_MAPE = Decimal("0.20")

#: 历史取多少周。8 周是需求里的演示数据量，也正好让每个星期几有 8 个样本。
HISTORY_WEEKS = 8

#: 哪些异常标记会让那天不进历史序列
EXCLUDED_FLAGS: tuple[str, ...] = (
    AnomalyFlag.RECEPTION.value,
    AnomalyFlag.SUSPENDED.value,
    AnomalyFlag.EQUIPMENT_FAILURE.value,
)


def run_forecast(
    session: Session,
    *,
    on_date: date,
    meal_type: MealType = MealType.LUNCH,
    dish_ids: Sequence[UUID] | None = None,
) -> ForecastRunResult:
    """预测某天某一餐每道菜的份数，并汇总出采购建议单。

    `dish_ids` 给定时按这几道菜预测与汇总（合并页用它：采购按推荐选出的菜算）；
    不给则沿用旧行为——采购按当天菜单、没有菜单就按上周同一天实际供应的菜。
    """
    prediction = predict_dishes(session, on_date=on_date, meal_type=meal_type, dish_ids=dish_ids)
    if dish_ids is not None:
        planned_ids, basis_date, basis = list(dish_ids), on_date, "RECOMMENDATION"
    else:
        planned_ids, basis_date, basis = _planned_dishes(
            session, on_date=on_date, meal_type=meal_type
        )
    planned = set(planned_ids)

    forecasts = [
        DishForecast(
            dish_id=str(dish.dish_id),
            dish_name=dish.dish_name,
            category_label=dish.category_label,
            cooking_method_label=dish.cooking_method_label,
            predicted_servings=str(dish.predicted),
            ci_lower=str(dish.lower),
            ci_upper=str(dish.upper),
            baseline=str(dish.baseline),
            adjustment=str(dish.adjustment),
            basis=dish.basis,
            basis_label=dish.basis_label,
            samples=[
                ForecastSample(date=when, servings=str(value)) for when, value in dish.samples
            ],
            planned=dish.dish_id in planned,
        )
        for dish in prediction.dishes
    ]

    persist_predictions(session, prediction, on_date=on_date, meal_type=meal_type)
    session.commit()

    requirements, total_cost = build_purchase_list(
        session,
        servings_by_dish={
            dish_id: value for dish_id, value in prediction.servings.items() if dish_id in planned
        },
    )
    logger.info("预测完成：%s %s，%d 道菜", on_date, meal_type.label, len(forecasts))
    return ForecastRunResult(
        date=on_date,
        meal_type=meal_type,
        meal_type_label=meal_type.label,
        model_version=strategy.MODEL_VERSION,
        basis_date=basis_date,
        basis=basis,
        basis_label=(
            "当天已排菜单" if basis == "MENU" else "上周同一天实际供应的菜品（菜单按轮换推定）"
        ),
        dishes=sorted(forecasts, key=lambda item: Decimal(item.predicted_servings), reverse=True),
        requirements=requirements,
        total_cost=total_cost,
        calendar_notes=[prediction.calendar_note] if prediction.calendar_note else [],
        skipped=prediction.skipped,
        note=(
            "预测份数 = 最近 6 个同星期几的份数平均 × 日历修正系数；"
            "区间来自历史离散程度，并保底 ±10%。"
            "标了异常、临时替换与份数为 0 的日子不进历史序列。"
        ),
    )


def _forecast_rows(
    prediction: PredictionSet, only: Collection[UUID] | None = None
) -> list[dict[str, object]]:
    """把预测结果整理成落库用的行。快照自带依据，事后复盘不必再猜。"""
    return [
        {
            "dish_id": dish.dish_id,
            "predicted_servings": dish.predicted,
            "ci_lower": dish.lower,
            "ci_upper": dish.upper,
            "features": {
                "model": "同星期移动平均 × 日历修正",
                "baseline": str(dish.baseline),
                "adjustment": str(dish.adjustment),
                "samples": [
                    {"date": when.isoformat(), "servings": str(value)}
                    for when, value in dish.samples
                ],
                "calendar_note": dish.calendar_note,
            },
        }
        for dish in prediction.dishes
        if only is None or dish.dish_id in only
    ]


def persist_predictions(
    session: Session,
    prediction: PredictionSet,
    *,
    on_date: date,
    meal_type: MealType,
    only: Collection[UUID] | None = None,
) -> None:
    """把预测结果落库（同一日期同模型版本整份替换）。

    合并页与预测接口共用它：两个入口算出来的是同一件事，
    落库的口径就不能两样，否则回看时无法判断某一行的依据来自哪次生成。

    `only` 限定只落这几道菜——预测表记的是「这一餐要做的菜的份数」，
    把候选里没入选的也塞进去，回看时会以为那天要做十几道菜。
    """
    repository.replace_forecasts(
        session,
        on_date=on_date,
        meal_type=meal_type,
        model_version=strategy.MODEL_VERSION,
        rows=_forecast_rows(prediction, only),
    )


@dataclass(frozen=True, slots=True)
class PredictedDish:
    """一道菜的份数预测。合并页与预测页共用它，避免两处各拼一遍。"""

    dish_id: UUID
    dish_name: str
    category_label: str
    cooking_method_label: str
    predicted: Decimal
    lower: Decimal
    upper: Decimal
    baseline: Decimal
    adjustment: Decimal
    basis: str
    basis_label: str
    samples: tuple[tuple[date, Decimal], ...]
    calendar_note: str | None


@dataclass(frozen=True, slots=True)
class PredictionSet:
    dishes: list[PredictedDish]
    #: 历史不足、预测不出来的菜名——如实列出，不给凑出来的数字
    skipped: list[str]
    calendar_note: str | None

    @property
    def servings(self) -> dict[UUID, Decimal]:
        return {dish.dish_id: dish.predicted for dish in self.dishes}


def predict_dishes(
    session: Session,
    *,
    on_date: date,
    meal_type: MealType = MealType.LUNCH,
    dish_ids: Sequence[UUID] | None = None,
) -> PredictionSet:
    """按「同星期移动平均 × 日历修正」预测每道菜的份数，**逐菜独立**。

    逐菜独立这点很关键：它意味着**可以先把所有候选菜的份数都预测出来**，
    再拿这些份数去评估营养、选菜——不需要先知道菜单。否则「推荐要份数、份数要菜单」
    就成了死循环。

    `dish_ids` 给定时只预测这几道（合并页用它，份数按推荐选出的菜算）；
    不给则预测所有有历史的菜（预测页的旧行为）。
    """
    start = on_date - timedelta(weeks=HISTORY_WEEKS)
    context = strategy.day_context(
        on_date, repository.load_holidays(session, start=start, end=on_date)
    )
    history = repository.load_dish_history(session, start=start, end=on_date - timedelta(days=1))
    dishes = repository.load_active_dishes(session)
    profile = strategy.weekday_profile(
        [
            [strategy.HistoryPoint(day, servings) for day, servings in points]
            for points in history.values()
        ]
    )

    wanted = set(dish_ids) if dish_ids is not None else None
    predictions: list[PredictedDish] = []
    skipped: list[str] = []
    for dish_id, dish in dishes.items():
        if wanted is not None and dish_id not in wanted:
            continue
        points = history.get(dish_id)
        result = (
            strategy.forecast_dish(
                [strategy.HistoryPoint(day, servings) for day, servings in points],
                target=on_date,
                context=context,
                profile=profile,
            )
            if points
            else None
        )
        if result is None:
            skipped.append(dish.name)
            continue
        predictions.append(
            PredictedDish(
                dish_id=dish_id,
                dish_name=dish.name,
                category_label=dish.category.label,
                cooking_method_label=dish.cooking_method.label,
                predicted=result.predicted,
                lower=result.lower,
                upper=result.upper,
                baseline=result.baseline,
                adjustment=result.adjustment,
                basis=result.basis,
                basis_label=(
                    "同星期几平均"
                    if result.basis == "SAME_WEEKDAY"
                    else "全期平均 × 星期几规律（同星期样本不足）"
                ),
                samples=tuple((point.date, point.servings) for point in result.samples),
                calendar_note=result.calendar_note,
            )
        )
    return PredictionSet(
        dishes=sorted(predictions, key=lambda item: item.predicted, reverse=True),
        skipped=sorted(skipped),
        calendar_note=context.note,
    )


def _planned_dishes(
    session: Session, *, on_date: date, meal_type: MealType
) -> tuple[list[UUID], date, str]:
    """采购建议按哪一批菜算。

    当天已经排好菜单就用它；还没排（例如预测明天、而明天的菜单还没定）就沿用
    **上周同一天实际供应的菜**——食堂是一轮一轮转的，这比拿整个菜品库去汇总采购量靠谱得多。
    用的是哪一种，接口会明确写出来，不让看的人猜。
    """
    menu_day = repository.load_menu_day(session, on_date=on_date, meal_type=meal_type)
    if menu_day is not None:
        return repository.load_menu_dish_ids(session, menu_day.id), on_date, "MENU"
    fallback = on_date - timedelta(days=7)
    return (
        repository.load_served_dish_ids(session, on_date=fallback, meal_type=meal_type),
        fallback,
        "LAST_SAME_WEEKDAY",
    )


def build_purchase_list(
    session: Session, *, servings_by_dish: dict[UUID, Decimal]
) -> tuple[list[IngredientRequirement], str | None]:
    """由份数反推食材与调味料需求量，并按单价估算金额。

    采购单是给人拿去下单的，所以**按金额从大到小排**、**用量按公斤报**：
    按名称字母序排的单一列出去，最该先看的「牛肉买了多少钱」被埋在中间。
    """
    if not servings_by_dish:
        return [], None
    dish_ids = list(servings_by_dish)
    usage = repository.load_ingredient_usage(session, dish_ids)
    totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    prices: dict[str, Decimal | None] = {}

    for dish_id in dish_ids:
        servings = servings_by_dish[dish_id]
        for name, _unit, per_serving, price in usage.get(dish_id, []):
            totals[name] += per_serving * servings
            prices[name] = None if price is None else Decimal(price)

    requirements: list[IngredientRequirement] = []
    total_cost = Decimal("0")
    priced = False
    for name, grams in totals.items():
        # 按公斤报：下单是论公斤的，43101.6 克这种数字没人愿意换算
        quantity = (grams / Decimal("1000")).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        price = prices.get(name)
        # 单价是「元 / 公斤」、用量是克，所以除以 1000 再乘
        cost = None if price is None else quantity * price
        if cost is not None:
            total_cost += cost
            priced = True
        requirements.append(
            IngredientRequirement(
                name=name,
                unit="公斤",
                quantity=str(quantity),
                unit_price=None if price is None else str(price),
                estimated_cost=None if cost is None else str(cost.quantize(Decimal("0.01"))),
            )
        )
    # 按金额从大到小；没有单价的排最后（它们算不出金额，不能占着前排）
    requirements.sort(
        key=lambda row: (
            row.estimated_cost is None,
            -Decimal(row.estimated_cost or "0"),
            row.name,
        )
    )
    return requirements, str(total_cost.quantize(Decimal("0.01"))) if priced else None


def backtest(
    session: Session, *, days: int, meal_type: MealType = MealType.LUNCH
) -> BacktestResult:
    """回测：对过去 N 天的每一天，只用它**之前**的历史预测，再与实际份数比。

    这条「只用之前的数据」是回测能不能信的底线：拿包含当天的历史去预测当天，
    误差会好看得多，但那不是预测，是自证。
    """
    end = datetime.now(get_settings().timezone).date()
    start = end - timedelta(days=days - 1)
    history = repository.load_dish_history(
        session, start=start - timedelta(weeks=HISTORY_WEEKS), end=end
    )
    profile = strategy.weekday_profile(
        [
            [strategy.HistoryPoint(day, servings) for day, servings in points]
            for points in history.values()
        ]
    )
    holidays = repository.load_holidays(session, start=start - timedelta(weeks=1), end=end)

    points: list[BacktestPoint] = []
    all_pairs: list[tuple[Decimal, Decimal]] = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        context = strategy.day_context(day, holidays)
        pairs: list[tuple[Decimal, Decimal]] = []
        for dish_history in history.values():
            actual = next((value for when, value in dish_history if when == day), None)
            if actual is None:
                continue
            earlier = [
                strategy.HistoryPoint(when, value) for when, value in dish_history if when < day
            ]
            result = strategy.forecast_dish(earlier, target=day, context=context, profile=profile)
            if result is not None:
                pairs.append((actual, result.predicted))
        all_pairs.extend(pairs)
        daily = strategy.mean_absolute_percentage_error(pairs)
        points.append(
            BacktestPoint(
                date=day, dish_count=len(pairs), mape=None if daily is None else str(daily)
            )
        )

    overall = strategy.mean_absolute_percentage_error(all_pairs)
    return BacktestResult(
        model_version=strategy.MODEL_VERSION,
        days=days,
        usable_days=sum(1 for point in points if point.dish_count > 0),
        start=start,
        end=end,
        mape=None if overall is None else str(overall),
        target_mape=str(TARGET_MAPE),
        passed=overall is not None and overall <= TARGET_MAPE,
        points=points,
        note=(
            "每一天都只用它之前的历史做预测，不把当天算进去；"
            "剔除异常日、临时替换与份数为 0 的记录。"
            "注意：回测的前段没有足够的历史可供参照，因此能算出结果的天数少于回测天数——"
            "这是数据长度决定的，不是模型挑着算。"
        ),
    )


def list_holidays(session: Session, *, year: int) -> HolidayPage:
    rows = repository.load_holiday_rows(session, year=year)
    unverified = sum(1 for row in rows if not row.is_verified)
    return HolidayPage(
        year=year,
        items=[_holiday_read(row) for row in rows],
        unverified_count=unverified,
        note=(
            "内置日历只放了法定节日的公历日期，放假区间与调休上班日必须对照"
            "国务院办公厅通知核对；核对后把条目改成已核对，预测才会按它修正。"
            if unverified
            else "全部条目已核对。"
        ),
    )


def update_holiday(session: Session, *, holiday_id: UUID, payload: HolidayWrite) -> HolidayRead:
    row = session.get(Holiday, holiday_id)
    if row is None:
        raise NotFoundError("节假日条目不存在")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(row, field, value)
    session.commit()
    return _holiday_read(row)


def _holiday_read(row: Holiday) -> HolidayRead:
    return HolidayRead(
        id=str(row.id),
        date=row.date,
        name=row.name,
        kind=row.kind,
        kind_label=HolidayKind(row.kind).label,
        is_verified=row.is_verified,
        source_note=row.source_note,
    )

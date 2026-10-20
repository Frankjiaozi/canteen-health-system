"""管理端看板的聚合逻辑。"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.analytics import repository
from app.modules.analytics.schemas import (
    CompliancePoint,
    ComplianceResponse,
    DashboardSummary,
    MenuOverviewDay,
    MenuOverviewDish,
    MenuOverviewMeal,
    MenuOverviewResponse,
    NutrientAmount,
    PerCapitaResponse,
    StandardTarget,
    TrendPoint,
    TrendsResponse,
    WastePoint,
    WasteResponse,
)
from app.modules.collection.models import DailyLog
from app.modules.nutrition.models import NutritionStandard
from app.modules.nutrition.schemas import StandardComparison
from app.shared.enums import MealType, StandardCode
from app.shared.nutrients import (
    FIELD_TO_NUTRIENT_CODE,
    NUTRIENT_FIELDS,
    NUTRIENT_SCALES,
    NUTRIENT_UNITS,
)
from app.shared.standards import (
    STATUS_OK,
    compare_to_standard,
    mean,
    quantize,
    sum_per_capita_across_meals,
)

TREND_CODES: tuple[StandardCode, ...] = (
    StandardCode.EDIBLE_OIL,
    StandardCode.SALT,
    StandardCode.ADDED_SUGAR,
)

#: 三种调料的每人每日用量字段，与 TREND_CODES 一一对应
SEASONING_FIELDS: dict[StandardCode, str] = {
    StandardCode.EDIBLE_OIL: "oil_total_g",
    StandardCode.SALT: "salt_total_g",
    StandardCode.ADDED_SUGAR: "sugar_total_g",
}

BASIS_NOTE = (
    "人均营养摄入取每道菜当日证据最强的一份：抽样称重实测 > 当日闭环校准 > 标准配方理论值；"
    "食盐、烹调油与添加糖的对照基于当日实际投料量除以就餐人次。"
    "两者来源不同，不宜混读——前者反映菜品实际的营养供给，后者反映后厨的实际投放。"
)


def _range(days: int) -> tuple[date, date]:
    today = datetime.now(get_settings().timezone).date()
    return today - timedelta(days=days - 1), today


def build_menu_overview(session: Session) -> MenuOverviewResponse:
    """今明两天菜单。只读菜单日；没有同步/发布过的计划不会出现在这里。"""
    today = datetime.now(get_settings().timezone).date()
    tomorrow = today + timedelta(days=1)
    menus = repository.load_menu_days(session, start=today, end=tomorrow)
    logs = repository.load_daily_logs(session, start=today, end=tomorrow)
    grouped = repository.load_menu_items(session, [row.id for row in menus])
    menu_by_slot = {(row.date, row.meal_type): row for row in menus}
    log_by_slot = {(row.date, row.meal_type): row for row in logs}
    status_labels = {
        "PLANNED": "计划供应",
        "ACTUAL": "实际供应",
        "NOT_PLANNED": "未安排",
    }
    days: list[MenuOverviewDay] = []
    for target, label in ((today, "今天"), (tomorrow, "明天")):
        meals: list[MenuOverviewMeal] = []
        for meal_type in (MealType.BREAKFAST, MealType.LUNCH, MealType.DINNER):
            menu = menu_by_slot.get((target, meal_type))
            log = log_by_slot.get((target, meal_type))
            status = "NOT_PLANNED" if menu is None else "ACTUAL" if log else "PLANNED"
            rows = grouped.get(menu.id, []) if menu is not None else []
            meals.append(
                MenuOverviewMeal(
                    meal_type=meal_type,
                    meal_type_label=meal_type.label,
                    status=status,
                    status_label=status_labels[status],
                    diner_count=None if log is None else log.diner_count,
                    dishes=[
                        MenuOverviewDish(
                            dish_id=str(dish.id),
                            name=dish.name,
                            category_label=dish.category.label,
                            cooking_method_label=dish.cooking_method.label,
                            planned_servings=(
                                None
                                if item.planned_servings is None
                                else str(item.planned_servings)
                            ),
                        )
                        for dish, item in rows
                    ],
                )
            )
        days.append(MenuOverviewDay(date=target, day_label=label, meals=meals))
    return MenuOverviewResponse(today=today, tomorrow=tomorrow, days=days)


def _daily_seasoning_actuals(
    logs: list[DailyLog],
) -> dict[date, dict[StandardCode, Decimal | None]]:
    grouped: dict[date, list[DailyLog]] = defaultdict(list)
    for log in logs:
        grouped[log.date].append(log)

    return {
        day: {
            code: sum_per_capita_across_meals(day_logs, field)
            for code, field in SEASONING_FIELDS.items()
        }
        for day, day_logs in grouped.items()
    }


def _standard_row(standard: NutritionStandard, actual: Decimal | None) -> StandardComparison:
    return StandardComparison(
        code=standard.code.value,
        label=standard.name,
        unit=standard.unit,
        target_min=None if standard.target_min is None else str(standard.target_min),
        target_max=None if standard.target_max is None else str(standard.target_max),
        actual=None if actual is None else str(actual),
        status=compare_to_standard(
            target_min=standard.target_min, target_max=standard.target_max, actual=actual
        ),
        source=standard.source,
        source_quote=standard.source_quote,
    )


def _all_daily_actuals(
    session: Session, *, start: date, end: date
) -> tuple[dict[date, dict[StandardCode, Decimal | None]], list[NutritionStandard]]:
    logs = repository.load_daily_logs(session, start=start, end=end)
    actuals = _daily_seasoning_actuals(logs)
    variety = repository.load_day_ingredient_counts(session, start=start, end=end)

    for day in {log.date for log in logs} | set(variety):
        bucket = actuals.setdefault(day, {})
        bucket[StandardCode.FOOD_VARIETY] = Decimal(variety[day]) if day in variety else None

    return actuals, repository.load_active_standards(session)


def build_trends(session: Session, *, days: int) -> TrendsResponse:
    start, end = _range(days)
    logs = repository.load_daily_logs(session, start=start, end=end)
    grouped: dict[date, list[DailyLog]] = defaultdict(list)
    for log in logs:
        grouped[log.date].append(log)

    points: list[TrendPoint] = []
    for day in sorted(grouped):
        day_logs = grouped[day]
        per_capita = {
            code: sum_per_capita_across_meals(day_logs, field)
            for code, field in SEASONING_FIELDS.items()
        }
        oil_total = _total(day_logs, "oil_total_g")
        salt_total = _total(day_logs, "salt_total_g")
        sugar_total = _total(day_logs, "sugar_total_g")
        points.append(
            TrendPoint(
                date=day,
                diner_count=sum(log.diner_count for log in day_logs),
                oil_total_g=None if oil_total is None else str(oil_total),
                salt_total_g=None if salt_total is None else str(salt_total),
                sugar_total_g=None if sugar_total is None else str(sugar_total),
                oil_per_capita_g=_opt_str(per_capita[StandardCode.EDIBLE_OIL]),
                salt_per_capita_g=_opt_str(per_capita[StandardCode.SALT]),
                sugar_per_capita_g=_opt_str(per_capita[StandardCode.ADDED_SUGAR]),
            )
        )

    standards = repository.load_active_standards(session)
    targets = [
        StandardTarget(
            code=item.code.value,
            label=item.name,
            unit=item.unit,
            target_min=None if item.target_min is None else str(item.target_min),
            target_max=None if item.target_max is None else str(item.target_max),
        )
        for item in standards
        if item.code in TREND_CODES
    ]

    return TrendsResponse(days=days, start=start, end=end, points=points, targets=targets)


def build_per_capita(session: Session, *, days: int) -> PerCapitaResponse:
    start, end = _range(days)
    totals = repository.load_day_per_capita_totals(session, start=start, end=end)
    actuals, standards = _all_daily_actuals(session, start=start, end=end)
    logs = repository.load_daily_logs(session, start=start, end=end)
    diner_by_day: dict[date, int] = defaultdict(int)
    for log in logs:
        diner_by_day[log.date] += log.diner_count

    latest_date = max(totals) if totals else None
    latest_actuals = actuals.get(latest_date, {}) if latest_date is not None else {}

    return PerCapitaResponse(
        days=days,
        start=start,
        end=end,
        latest_date=latest_date,
        latest_diner_count=None if latest_date is None else diner_by_day.get(latest_date),
        latest=_amounts(totals.get(latest_date) if latest_date else None),
        average=_averages(totals),
        comparisons=[_standard_row(item, latest_actuals.get(item.code)) for item in standards],
        basis_note=BASIS_NOTE,
    )


def build_compliance(session: Session, *, days: int) -> ComplianceResponse:
    start, end = _range(days)
    actuals, standards = _all_daily_actuals(session, start=start, end=end)

    points: list[CompliancePoint] = []
    for day in sorted(actuals):
        items = [_standard_row(item, actuals[day].get(item.code)) for item in standards]
        comparable = [item for item in items if item.status != "unknown"]
        compliant = sum(1 for item in comparable if item.status == STATUS_OK)
        points.append(
            CompliancePoint(
                date=day,
                compliant=compliant,
                total=len(comparable),
                rate=_ratio(compliant, len(comparable)),
                items=items,
            )
        )

    overall = (
        _ratio(
            sum(point.compliant for point in points),
            sum(point.total for point in points),
        )
        if points
        else None
    )
    return ComplianceResponse(days=days, start=start, end=end, points=points, overall_rate=overall)


def build_waste(session: Session, *, days: int) -> WasteResponse:
    start, end = _range(days)
    rows = repository.load_waste_rows(session, start=start, end=end)

    points: list[WastePoint] = []
    ratios: list[Decimal] = []
    for day, produced, leftover in rows:
        produced_decimal = Decimal(produced)
        leftover_decimal = Decimal("0") if leftover is None else Decimal(leftover)
        ratio = (
            Decimal("0")
            if produced_decimal == 0
            else quantize(leftover_decimal / produced_decimal, 4)
        )
        ratios.append(ratio)
        points.append(
            WastePoint(
                date=day,
                produced_weight_g=str(produced_decimal),
                leftover_weight_g=str(leftover_decimal),
                waste_ratio=str(ratio),
            )
        )

    average = mean(ratios)
    return WasteResponse(
        days=days,
        start=start,
        end=end,
        points=points,
        average_ratio=None if average is None else str(quantize(average, 4)),
    )


def build_summary(session: Session, *, days: int) -> DashboardSummary:
    start, end = _range(days)
    trends = build_trends(session, days=days)
    waste = build_waste(session, days=days)
    compliance = build_compliance(session, days=days)
    variety = repository.load_day_ingredient_counts(session, start=start, end=end)

    points = trends.points
    avg_diner = int(mean([Decimal(p.diner_count) for p in points]) or 0)
    latest_rate = compliance.points[-1].rate if compliance.points else None

    return DashboardSummary(
        days=days,
        start=start,
        end=end,
        days_with_records=len(points),
        avg_diner_count=avg_diner,
        avg_salt_per_capita_g=_mean_str(
            [Decimal(p.salt_per_capita_g) for p in points if p.salt_per_capita_g is not None]
        ),
        avg_oil_per_capita_g=_mean_str(
            [Decimal(p.oil_per_capita_g) for p in points if p.oil_per_capita_g is not None]
        ),
        avg_added_sugar_per_capita_g=_mean_str(
            [Decimal(p.sugar_per_capita_g) for p in points if p.sugar_per_capita_g is not None]
        ),
        avg_waste_ratio=waste.average_ratio,
        avg_dish_variety=_mean_str([Decimal(count) for count in variety.values()]),
        latest_compliance_rate=latest_rate,
    )


def _total(logs: list[DailyLog], field: str) -> Decimal | None:
    values = [getattr(log, field) for log in logs]
    if not values or any(value is None for value in values):
        return None
    return quantize(sum(values, Decimal("0")), 2)


def _opt_str(value: object) -> str | None:
    return None if value is None else str(value)


def _amounts(totals: dict[str, str] | None) -> list[NutrientAmount]:
    return [
        NutrientAmount(
            code=FIELD_TO_NUTRIENT_CODE[field].value,
            label=FIELD_TO_NUTRIENT_CODE[field].label,
            unit=NUTRIENT_UNITS[field],
            digits=NUTRIENT_SCALES[field],
            value=_scaled(totals.get(field), NUTRIENT_SCALES[field]) if totals else None,
        )
        for field in NUTRIENT_FIELDS
    ]


def _averages(totals: dict[date, dict[str, str]]) -> list[NutrientAmount]:
    return [
        NutrientAmount(
            code=FIELD_TO_NUTRIENT_CODE[field].value,
            label=FIELD_TO_NUTRIENT_CODE[field].label,
            unit=NUTRIENT_UNITS[field],
            digits=NUTRIENT_SCALES[field],
            value=_mean_str(
                [Decimal(day[field]) for day in totals.values() if day.get(field) is not None]
            ),
        )
        for field in NUTRIENT_FIELDS
    ]


def _scaled(value: str | None, digits: int) -> str | None:
    if value is None:
        return None
    return str(quantize(Decimal(value), digits))


def _mean_str(values: list[Decimal]) -> str | None:
    average = mean(values)
    return None if average is None else str(quantize(average, 2))


def _ratio(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0.0000"
    return str(
        (Decimal(numerator) / Decimal(denominator)).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )
    )

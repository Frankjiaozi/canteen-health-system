"""回测质量报告：同一历史切分下比较“无日历修正”基线与当前算法。"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from decimal import Decimal

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.modules.forecast import repository, strategy
from app.shared.enums import MealType


def _pairs_for_day(
    history,
    *,
    day,
    context,
    profile,
) -> tuple[list[tuple[Decimal, Decimal]], list[tuple[Decimal, Decimal]]]:
    current: list[tuple[Decimal, Decimal]] = []
    baseline: list[tuple[Decimal, Decimal]] = []
    no_calendar = strategy.DayContext()
    for points in history.values():
        actual = next((value for when, value in points if when == day), None)
        if actual is None:
            continue
        earlier = [strategy.HistoryPoint(when, value) for when, value in points if when < day]
        adjusted = strategy.forecast_dish(earlier, target=day, context=context, profile=profile)
        plain = strategy.forecast_dish(earlier, target=day, context=no_calendar, profile=profile)
        if adjusted is not None:
            current.append((actual, adjusted.predicted))
        if plain is not None:
            baseline.append((actual, plain.predicted))
    return current, baseline


def build_report(*, days: int, meal_type: MealType) -> dict:
    end = datetime.now(get_settings().timezone).date()
    start = end - timedelta(days=days - 1)
    session = get_session_factory()()
    try:
        history = repository.load_dish_history(
            session,
            start=start - timedelta(weeks=8),
            end=end,
            meal_type=meal_type,
        )
        holidays = repository.load_holidays(session, start=start - timedelta(weeks=1), end=end)
        database = session.bind.url.database if session.bind is not None else None
    finally:
        session.close()
    current_pairs: list[tuple[Decimal, Decimal]] = []
    baseline_pairs: list[tuple[Decimal, Decimal]] = []
    points: list[dict] = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        history_before_day = [
            [strategy.HistoryPoint(when, value) for when, value in rows if when < day]
            for rows in history.values()
        ]
        profile = strategy.weekday_profile(history_before_day)
        context = strategy.day_context(day, holidays)
        current, baseline = _pairs_for_day(history, day=day, context=context, profile=profile)
        current_pairs.extend(current)
        baseline_pairs.extend(baseline)
        points.append(
            {
                "date": str(day),
                "dish_count": len(current),
                "mape": str(strategy.mean_absolute_percentage_error(current)) if current else None,
            }
        )
    current_mape = strategy.mean_absolute_percentage_error(current_pairs)
    baseline_mape = strategy.mean_absolute_percentage_error(baseline_pairs)
    return {
        "generated_at": datetime.now(get_settings().timezone).isoformat(),
        "database": database,
        "meal_type": meal_type.value,
        "days": days,
        "start": str(start),
        "end": str(end),
        "usable_days": sum(1 for point in points if point["dish_count"] > 0),
        "current": {
            "model": strategy.MODEL_VERSION,
            "mape": None if current_mape is None else str(current_mape),
            "samples": len(current_pairs),
        },
        "baseline": {
            "model": "same-weekday-without-calendar",
            "mape": None if baseline_mape is None else str(baseline_mape),
            "samples": len(baseline_pairs),
        },
        "target_mape": "0.20",
        "passed": current_mape is not None and current_mape <= Decimal("0.20"),
        "note": (
            "当前算法 = 同星期历史 × 日历修正；基线 = 相同历史切分、相同回退规则，"
            "但不应用节假日/调休修正。两者只在此报告的同一数据切分上比较，"
            "不代表真实食堂的生产准确率。"
        ),
        "points": points,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=56)
    parser.add_argument("--meal-type", choices=[item.value for item in MealType], default="LUNCH")
    args = parser.parse_args()
    print(
        json.dumps(
            build_report(days=args.days, meal_type=MealType(args.meal_type)),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()

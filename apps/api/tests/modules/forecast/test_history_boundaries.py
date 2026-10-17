"""预测只使用同餐次的过去记录；后来的极端值不能改写过去的回测。"""

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from app.modules.collection.models import DailyLog, DailyLogItem
from app.modules.dish.models import Dish
from app.modules.forecast import service
from app.modules.forecast.models import Holiday
from app.modules.recommendation import repository as recommendation
from app.shared.enums import HolidayKind, MealType
from sqlalchemy import select

from tests.helpers import today_local


def test_lunch_forecast_does_not_mix_in_dinner(db_session):
    today = today_local()
    dish = db_session.scalar(select(Dish).order_by(Dish.name).limit(1))
    before = service.predict_dishes(
        db_session, on_date=today + timedelta(days=1), meal_type=MealType.LUNCH, dish_ids=[dish.id]
    )
    assert before.dishes
    for offset in range(1, 15):
        log = DailyLog(
            date=today - timedelta(days=offset), meal_type=MealType.DINNER, diner_count=9000
        )
        db_session.add(log)
        db_session.flush()
        db_session.add(DailyLogItem(daily_log_id=log.id, dish_id=dish.id, servings_produced=9000))
    db_session.flush()
    after = service.predict_dishes(
        db_session, on_date=today + timedelta(days=1), meal_type=MealType.LUNCH, dish_ids=[dish.id]
    )
    dinner = service.predict_dishes(
        db_session, on_date=today + timedelta(days=1), meal_type=MealType.DINNER, dish_ids=[dish.id]
    )
    assert after.dishes[0].predicted == before.dishes[0].predicted
    assert dinner.dishes[0].predicted == Decimal("9000.00")


def test_latest_diners_are_before_target_and_match_the_meal(db_session):
    target = today_local() + timedelta(days=20)
    db_session.add_all(
        [
            DailyLog(date=target - timedelta(days=2), meal_type=MealType.DINNER, diner_count=321),
            DailyLog(date=target - timedelta(days=1), meal_type=MealType.LUNCH, diner_count=999),
            DailyLog(date=target, meal_type=MealType.DINNER, diner_count=888),
        ]
    )
    db_session.flush()
    assert (
        recommendation.load_latest_diner_count(
            db_session, on_date=target, meal_type=MealType.DINNER
        )
        == 321
    )


def test_unverified_calendar_does_not_change_a_forecast(db_session):
    day = today_local() + timedelta(days=72)
    row = Holiday(date=day, name="待核对测试日", kind=HolidayKind.HOLIDAY, is_verified=False)
    db_session.add(row)
    db_session.flush()
    assert day not in service.repository.load_holidays(db_session, start=day, end=day)
    row.is_verified = True
    db_session.flush()
    assert (
        service.repository.load_holidays(db_session, start=day, end=day)[day] == HolidayKind.HOLIDAY
    )


def test_later_extreme_record_cannot_change_earlier_backtest(monkeypatch, db_session):
    end = today_local()
    first = end - timedelta(days=6)
    key = uuid4()
    history = {
        key: [(first - timedelta(days=i), Decimal("100")) for i in range(1, 15)]
        + [(first + timedelta(days=i), Decimal("100")) for i in range(7)]
    }
    monkeypatch.setattr(service.repository, "load_dish_history", lambda *args, **kwargs: history)
    monkeypatch.setattr(service.repository, "load_holidays", lambda *args, **kwargs: {})
    before = service.backtest(db_session, days=7)
    history[key][-1] = (end, Decimal("100000"))
    after = service.backtest(db_session, days=7)
    assert before.points[0].mape is not None
    assert [point.mape for point in before.points[:-1]] == [
        point.mape for point in after.points[:-1]
    ]

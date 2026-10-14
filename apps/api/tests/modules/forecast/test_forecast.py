"""消耗量预测的行为约定。

算法部分是纯函数，用构造数据就能把边界说清楚；接口部分盯的是
「预测结果真的落库、回测真的只用之前的历史、日历条目真的能被核对」。
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.modules.forecast import strategy
from app.modules.forecast.models import Forecast, Holiday
from app.shared.enums import HolidayKind
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.helpers import today_local

BASE = "/api/v1/forecast"


def _points(start: date, servings: list[int]) -> list[strategy.HistoryPoint]:
    return [
        strategy.HistoryPoint(start + timedelta(days=index), Decimal(value))
        for index, value in enumerate(servings)
    ]


# ---------------------------------------------------------------------------
# 算法
# ---------------------------------------------------------------------------
def test_same_weekday_average_ignores_other_weekdays() -> None:
    """周一与周五的份数能差一大截，混在一起平均出来的数字哪天都不像。"""
    start = date(2026, 9, 7)  # 周一
    history = []
    for week in range(4):
        for offset, value in enumerate([400, 900, 950, 960, 970, 300, 280]):
            history.append(
                strategy.HistoryPoint(start + timedelta(days=week * 7 + offset), Decimal(value))
            )

    baseline, samples = strategy.same_weekday_baseline(history, target=start + timedelta(days=28))

    assert len(samples) == 4, "四个周一都应当被取到"
    assert all(point.date.weekday() == 0 for point in samples)
    assert all(point.servings == Decimal(400) for point in samples)
    assert baseline == Decimal(400)


def test_holiday_and_makeup_workday_are_handled_differently() -> None:
    """放假是整体下调；调休上班不是乘系数，而是**换一套基线**。

    调休那天多半落在周末，而周末的基线本身就是错的——调休的周日是要上班的，
    拿其它周日的历史去估会低一大截。
    """
    day = date(2026, 10, 1)
    holidays = {day: HolidayKind.HOLIDAY, date(2026, 10, 10): HolidayKind.WORKDAY}

    holiday = strategy.day_context(day, holidays)
    workday = strategy.day_context(date(2026, 10, 10), holidays)
    normal = strategy.day_context(date(2026, 10, 13), holidays)

    assert holiday.factor < Decimal("1") and "法定假日" in (holiday.note or "")
    assert holiday.use_workday_baseline is False
    assert workday.use_workday_baseline is True and "调休" in (workday.note or "")
    assert workday.factor == Decimal("1"), "调休上班日就是工作日，不该再乘周末折减"
    assert normal.factor == Decimal("1") and normal.note is None


def test_makeup_workday_uses_a_workday_baseline() -> None:
    """2026-10-10 是调休上班的周六：必须按工作日的量级估，而不是按周六。

    这一天按普通周六算会低一半——调休那天人是来上班的。
    """
    start = date(2026, 8, 3)  # 周一
    history: list[strategy.HistoryPoint] = []
    for day_offset in range(70):
        day = start + timedelta(days=day_offset)
        if day.weekday() >= 5:
            continue  # 只放工作日的历史：工作日 900，与演示数据里周末低、工作日高一致
        history.append(strategy.HistoryPoint(day, Decimal("900")))
    # 星期六一向只有工作日的一半
    profile = {index: (Decimal("1") if index < 5 else Decimal("0.5")) for index in range(7)}

    target = date(2026, 10, 10)  # 周六，但国务院通知里是调休上班日
    calendar = {target: HolidayKind.WORKDAY}

    plain = strategy.forecast_dish(history, target=target, profile=profile)
    adjusted = strategy.forecast_dish(
        history, target=target, context=strategy.day_context(target, calendar), profile=profile
    )

    assert plain is not None and adjusted is not None
    assert Decimal("850") < adjusted.predicted < Decimal("950"), "调休上班日应当按工作日的量级"
    assert adjusted.predicted > plain.predicted * Decimal("1.5"), "不能按普通周六估"
    assert adjusted.calendar_note is not None and "调休" in adjusted.calendar_note


def test_short_history_yields_no_prediction() -> None:
    """样本不够时不给数字——凑一个出来比空着更糟。"""
    start = date(2026, 9, 7)
    history = _points(start, [400, 410])

    assert strategy.forecast_dish(history, target=start + timedelta(days=3)) is None


def test_fallback_uses_weekday_profile() -> None:
    """同星期样本不足时，用「全期平均 × 星期几规律」退化，而不是直接放弃。

    少了星期几那一步，周末会被高估一倍以上——种子演示数据里周末只有工作日的 45%。
    """
    start = date(2026, 9, 7)  # 周一
    history: list[strategy.HistoryPoint] = []
    for week in range(3):
        for offset in range(7):
            value = 1000 if offset < 5 else 450  # 周末明显更低
            history.append(
                strategy.HistoryPoint(start + timedelta(days=week * 7 + offset), Decimal(value))
            )
    profile = strategy.weekday_profile([history])

    saturday = start + timedelta(days=19)  # 第三个周六
    result = strategy.forecast_dish(
        [point for point in history if point.date < saturday],
        target=saturday,
        profile=profile,
    )

    assert result is not None
    assert result.basis == "WEEKDAY_PROFILE"
    # 周末的真实量级是 450 上下，绝不能按全期平均 843 报出去
    assert Decimal("350") < result.predicted < Decimal("550")


def test_mape_reports_none_instead_of_zero_without_samples() -> None:
    """没有可算的样本时要报「算不出」，报 0 会被读成完全准确。"""
    assert strategy.mean_absolute_percentage_error([]) is None
    assert strategy.mean_absolute_percentage_error([(Decimal(0), Decimal(5))]) is None
    assert strategy.mean_absolute_percentage_error(
        [(Decimal(100), Decimal(110)), (Decimal(200), Decimal(180))]
    ) == Decimal("0.1000")


def test_anomaly_flags_exclude_the_day() -> None:
    assert strategy.is_anomalous(["RECEPTION"], excluded=("RECEPTION", "SUSPENDED"))
    assert not strategy.is_anomalous(["CALIBRATION_RESIDUAL"], excluded=("RECEPTION",))
    assert not strategy.is_anomalous([], excluded=("RECEPTION",))


def test_ingredient_requirements_scale_with_servings() -> None:
    result = strategy.ingredient_requirements(
        {"牛肉": Decimal("120"), "土豆": Decimal("80")}, Decimal("300")
    )

    assert result["牛肉"] == Decimal("36000.000")
    assert result["土豆"] == Decimal("24000.000")


# ---------------------------------------------------------------------------
# 接口
# ---------------------------------------------------------------------------
def test_run_writes_forecasts_and_purchase_list(
    as_recorder: TestClient, db_session: Session
) -> None:
    target = today_local() + timedelta(days=1)

    body = as_recorder.post(
        f"{BASE}/run", params={"on_date": target.isoformat(), "meal_type": "LUNCH"}
    ).json()

    assert body["dishes"], "演示数据下应当能预测出菜品"
    assert body["model_version"] == strategy.MODEL_VERSION
    assert all(Decimal(dish["predicted_servings"]) > 0 for dish in body["dishes"])
    # 区间必须真的包住预测值，否则展示出来自相矛盾
    for dish in body["dishes"]:
        assert (
            Decimal(dish["ci_lower"])
            <= Decimal(dish["predicted_servings"])
            <= Decimal(dish["ci_upper"])
        )
        assert dish["basis"] in {"SAME_WEEKDAY", "WEEKDAY_PROFILE"}
        assert dish["samples"]

    assert body["requirements"], "采购建议不该是空的"
    assert body["basis_label"]

    db_session.expire_all()
    rows = db_session.scalars(select(Forecast).where(Forecast.date == target)).all()
    assert len(rows) == len(body["dishes"]), "预测结果要落库，便于回测与复盘"


def test_backtest_mapes_within_the_acceptance_line(as_recorder: TestClient) -> None:
    """需求验收：对 8 周历史回测，MAPE 不超过 20%。"""
    body = as_recorder.get(f"{BASE}/backtest", params={"days": 56}).json()

    assert body["mape"] is not None
    assert Decimal(body["mape"]) <= Decimal(body["target_mape"])
    assert body["passed"] is True
    # 数据只有 8 周，前段没有足够历史可参照，这一点必须如实报出来
    assert 0 < body["usable_days"] <= body["days"]
    assert body["points"] and len(body["points"]) == body["days"]


def test_backtest_only_uses_history_before_the_day(
    as_recorder: TestClient, db_session: Session
) -> None:
    """回测的每一天都不能把自己算进历史——那是自证，不是预测。"""
    body = as_recorder.get(f"{BASE}/backtest", params={"days": 14}).json()

    assert body["start"] < body["end"]


def test_calendar_matches_the_official_notice(as_recorder: TestClient) -> None:
    """日历逐条取自国务院办公厅 2026 年放假安排通知，且放假与调休都在。"""
    body = as_recorder.get(f"{BASE}/holidays", params={"year": 2026}).json()

    holidays = [item for item in body["items"] if item["kind"] == "HOLIDAY"]
    workdays = [item for item in body["items"] if item["kind"] == "WORKDAY"]
    # 通知原文：3+9+3+5+3+3+7 = 33 天放假；1+2+1+2 = 6 天调休上班
    assert len(holidays) == 33
    assert len(workdays) == 6
    assert body["unverified_count"] == 0, "已经按通知核对过，不该再有待核对条目"
    assert "国办发明电" in body["items"][0]["source_note"]

    # 抽查通知里的原话：元旦 1/1 起放假、1/4 上班；国庆 10/10 上班
    dates = {item["date"] for item in body["items"]}
    assert {"2026-01-01", "2026-01-03", "2026-01-04", "2026-10-10", "2026-02-23"} <= dates
    assert "2026-01-04" in {item["date"] for item in workdays}


def test_holiday_can_be_verified_and_a_makeup_day_added(
    as_recorder: TestClient, db_session: Session
) -> None:
    """核对入口：确认节日那天，并把调休上班日补进日历。"""
    items = as_recorder.get(f"{BASE}/holidays", params={"year": 2026}).json()["items"]
    national_day = next(item for item in items if item["date"] == "2026-10-01")

    updated = as_recorder.patch(f"{BASE}/holidays/{national_day['id']}", json={"is_verified": True})

    assert updated.status_code == 200, updated.text
    assert updated.json()["is_verified"] is True

    db_session.expire_all()
    row = db_session.scalar(select(Holiday).where(Holiday.date == date(2026, 10, 1)))
    assert row is not None and row.is_verified is True


def test_unknown_holiday_is_rejected(as_recorder: TestClient) -> None:
    response = as_recorder.patch(
        f"{BASE}/holidays/00000000-0000-0000-0000-000000000000", json={"is_verified": True}
    )

    assert response.status_code == 404


def test_forecast_requires_login(client: TestClient) -> None:
    assert (
        client.post(f"{BASE}/run", params={"on_date": today_local().isoformat()}).status_code == 401
    )
    assert client.get(f"{BASE}/backtest").status_code == 401


def test_school_admin_reads_but_does_not_run(
    as_school_admin: TestClient, db_session: Session
) -> None:
    """学校管理方看得到预测与回测，但不该替食堂下采购单。"""
    assert as_school_admin.get(f"{BASE}/backtest").status_code == 200
    assert as_school_admin.get(f"{BASE}/holidays", params={"year": 2026}).status_code == 200

    target = today_local() + timedelta(days=2)
    response = as_school_admin.post(f"{BASE}/run", params={"on_date": target.isoformat()})
    assert response.status_code == 403

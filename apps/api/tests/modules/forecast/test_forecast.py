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


def test_holiday_and_makeup_workday_adjustments() -> None:
    day = date(2026, 10, 1)
    holidays = {day: HolidayKind.HOLIDAY, date(2026, 10, 10): HolidayKind.WORKDAY}

    down, note = strategy.day_adjustment(day, holidays)
    up, workday_note = strategy.day_adjustment(date(2026, 10, 10), holidays)
    flat, none_note = strategy.day_adjustment(date(2026, 10, 7), holidays)

    assert down < Decimal("1") and "法定假日" in (note or "")
    assert up > Decimal("1") and "调休" in (workday_note or "")
    assert flat == Decimal("1") and none_note is None


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


def test_holidays_are_listed_as_unverified(as_recorder: TestClient) -> None:
    body = as_recorder.get(f"{BASE}/holidays", params={"year": 2026}).json()

    assert len(body["items"]) == 7
    assert body["unverified_count"] == 7
    assert all(item["is_verified"] is False for item in body["items"])
    assert "国务院办公厅" in body["note"], "必须说清以什么为准"


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

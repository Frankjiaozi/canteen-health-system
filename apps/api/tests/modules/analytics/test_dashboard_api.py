"""管理端看板接口的行为约定。

重点：需要登录、聚合结果与手算一致、切换时间范围结果随之变化。
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

import pytest
from app.db.session import get_session_factory
from app.modules.collection.models import DailyLog, DailyLogItem
from app.modules.forecast.models import Forecast
from app.modules.menu.models import MenuDay, MenuDayItem
from app.modules.nutrition.models import DishNutrition
from app.modules.recommendation.models import MenuSuggestion
from app.shared.enums import NutrientCaliber
from app.shared.nutrients import NUTRIENT_FIELDS
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from tests.helpers import today_local

BASE = "/api/v1/dashboard"

#: 功能验证历史覆盖 8 周，接口的 days 参数与用例的统计窗口都取这个长度
SEEDED_WINDOW_DAYS = 56


@pytest.fixture(autouse=True)
def cleanup_tomorrow_plan() -> Iterator[None]:
    """看板菜单用例只碰明天，结束后清掉，避免给别的用例留下未来菜单。"""
    cutoff = today_local()
    yield
    with get_session_factory()() as session:
        log_ids = list(session.scalars(select(DailyLog.id).where(DailyLog.date > cutoff)))
        if log_ids:
            session.execute(delete(DailyLogItem).where(DailyLogItem.daily_log_id.in_(log_ids)))
        session.execute(delete(DailyLog).where(DailyLog.date > cutoff))
        menu_ids = list(session.scalars(select(MenuDay.id).where(MenuDay.date > cutoff)))
        if menu_ids:
            session.execute(delete(MenuDayItem).where(MenuDayItem.menu_day_id.in_(menu_ids)))
        session.execute(delete(MenuDay).where(MenuDay.date > cutoff))
        session.execute(delete(DishNutrition).where(DishNutrition.date > cutoff))
        session.execute(delete(Forecast).where(Forecast.date > cutoff))
        session.execute(delete(MenuSuggestion).where(MenuSuggestion.date > cutoff))
        session.commit()


def test_dashboard_requires_login(client: TestClient) -> None:
    for path in ("summary", "trends", "per-capita", "compliance", "waste", "menus"):
        assert client.get(f"{BASE}/{path}").status_code == 401


def test_school_admin_can_view_dashboard(as_school_admin: TestClient) -> None:
    assert as_school_admin.get(f"{BASE}/summary").status_code == 200


def test_summary_average_salt_matches_manual_calculation(
    as_recorder: TestClient, db_session: Session
) -> None:
    """人均食盐是「各餐各自除以本餐人次再按天取平均」，这里独立算一遍核对。"""
    by_day: dict[object, list[DailyLog]] = defaultdict(list)
    # 与接口用同一个统计窗口：接口按「最近 N 天」取，库里的记录却可能超出这个范围
    # （例如端到端用例造的未来日期），不加界就会算成两件事
    today = today_local()
    window_start = today - timedelta(days=SEEDED_WINDOW_DAYS - 1)
    for log in db_session.scalars(
        select(DailyLog).where(DailyLog.date >= window_start, DailyLog.date <= today)
    ):
        by_day[log.date].append(log)
    # 日人均值本身按两位小数对外（趋势图的点就是这个精度），汇总再对它取平均。
    # 手算也必须先落到同一精度，否则未舍入的日值平均后会在临界日差出 0.01。
    per_day = [
        sum((log.salt_total_g / Decimal(log.diner_count) for log in logs), Decimal("0")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        for logs in by_day.values()
        if logs
    ]
    expected = (sum(per_day) / Decimal(len(per_day))).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    # 功能验证历史是 8 周，因此显式按 8 周取，让统计窗口与库里的数据范围一致
    body = as_recorder.get(f"{BASE}/summary", params={"days": SEEDED_WINDOW_DAYS}).json()

    assert body["avg_salt_per_capita_g"] == str(expected)
    assert body["days_with_records"] == len(per_day)


def test_summary_reports_all_headline_metrics(as_recorder: TestClient) -> None:
    body = as_recorder.get(f"{BASE}/summary").json()

    assert body["days"] == 14
    assert body["avg_diner_count"] > 0
    assert body["avg_oil_per_capita_g"] is not None
    assert body["avg_added_sugar_per_capita_g"] is not None
    assert body["avg_waste_ratio"] is not None
    assert body["avg_dish_variety"] is not None
    assert body["latest_compliance_rate"] is not None


def test_trends_point_count_follows_the_range(as_recorder: TestClient) -> None:
    week = as_recorder.get(f"{BASE}/trends", params={"days": 7}).json()
    fortnight = as_recorder.get(f"{BASE}/trends", params={"days": 14}).json()

    assert week["days"] == 7
    assert len(week["points"]) == 7
    assert len(fortnight["points"]) == 14
    # 时间范围不同，起始日期必须跟着变
    assert week["start"] > fortnight["start"]
    assert week["end"] == fortnight["end"]


def test_trends_points_are_ordered_and_unique(as_recorder: TestClient) -> None:
    points = as_recorder.get(f"{BASE}/trends").json()["points"]
    dates = [point["date"] for point in points]

    assert dates == sorted(dates)
    assert len(set(dates)) == len(dates)


def test_trends_carry_target_lines_from_the_standards(as_recorder: TestClient) -> None:
    targets = {item["code"]: item for item in as_recorder.get(f"{BASE}/trends").json()["targets"]}

    assert set(targets) == {"SALT", "EDIBLE_OIL", "ADDED_SUGAR"}
    assert targets["SALT"]["target_max"] == "5.000"
    assert targets["EDIBLE_OIL"]["target_min"] == "25.000"


def test_trends_per_capita_is_derived_from_that_day(as_recorder: TestClient) -> None:
    points = as_recorder.get(f"{BASE}/trends", params={"days": 3}).json()["points"]

    for point in points:
        assert Decimal(point["salt_per_capita_g"]) > 0
        # 人均一定小于总量：一顿饭不可能人人都吃掉整锅
        assert Decimal(point["salt_per_capita_g"]) < Decimal(point["salt_total_g"])


def test_compliance_rate_is_a_fraction(as_recorder: TestClient) -> None:
    body = as_recorder.get(f"{BASE}/compliance").json()

    assert body["points"]
    for point in body["points"]:
        assert point["total"] > 0
        assert 0 <= Decimal(point["rate"]) <= 1
        assert len(point["items"]) == 4
        assert point["compliant"] <= point["total"]


def test_compliance_flags_too_much_salt(as_recorder: TestClient) -> None:
    """食盐超过每日 5 克必须被判为 over，而不是笼统的「不达标」。"""
    body = as_recorder.get(f"{BASE}/compliance").json()
    salt_items = [
        item for point in body["points"] for item in point["items"] if item["code"] == "SALT"
    ]

    assert salt_items
    for item in salt_items:
        if Decimal(item["actual"]) > Decimal("5.000"):
            assert item["status"] == "over"
        else:
            assert item["status"] == "ok"


def test_waste_ratio_is_leftover_over_produced(as_recorder: TestClient) -> None:
    points = as_recorder.get(f"{BASE}/waste").json()["points"]

    assert points
    for point in points:
        produced = Decimal(point["produced_weight_g"])
        leftover = Decimal(point["leftover_weight_g"])
        expected = (leftover / produced).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        assert Decimal(point["waste_ratio"]) == expected
        assert 0 <= Decimal(point["waste_ratio"]) <= 1


def test_per_capita_explains_its_basis(as_recorder: TestClient) -> None:
    """人均摄入与调料实际投放是两套来源，接口必须把口径讲清楚。"""
    body = as_recorder.get(f"{BASE}/per-capita").json()

    assert body["latest_date"] is not None
    assert body["latest_diner_count"] > 0
    assert len(body["latest"]) == 5
    assert len(body["average"]) == 5
    assert "抽样称重实测" in body["basis_note"]
    assert "理论值" in body["basis_note"]
    assert "实际投料量" in body["basis_note"]
    assert len(body["comparisons"]) == 4


def test_per_capita_sums_one_row_per_dish(as_recorder: TestClient, db_session: Session) -> None:
    """同一道菜当天可能有三份人均结果，只能取一份相加。

    三份全加进去等于把同一道菜算三遍，人均摄入会凭空翻两三倍——这种错不会报错，
    只会让看板上的数字悄悄偏大，所以必须有一条盯着它。
    """
    # 先跑一次当日闭环，保证每天至少有两份人均结果（理论 + 校准）可挑，
    # 否则这条测试在干净库上什么也没验到
    latest_log = db_session.scalar(
        select(DailyLog)
        .where(DailyLog.date <= today_local())
        .order_by(DailyLog.date.desc())
        .limit(1)
    )
    assert latest_log is not None
    as_recorder.post(
        "/api/v1/calibration/daily-closure",
        params={"on_date": latest_log.date.isoformat(), "meal_type": latest_log.meal_type.value},
    )

    body = as_recorder.get(f"{BASE}/per-capita", params={"days": 56}).json()
    assert body["latest_date"] is not None
    latest_date = date.fromisoformat(body["latest_date"])

    priority = {"SAMPLED": 0, "CALIBRATED": 1, "THEORETICAL": 2}
    rows = db_session.scalars(
        select(DishNutrition).where(
            DishNutrition.date == latest_date,
            DishNutrition.caliber == NutrientCaliber.PER_CAPITA,
        )
    ).all()
    assert rows, "最新一天应当有人均口径结果"

    best: dict[object, DishNutrition] = {}
    for row in rows:
        current = best.get(row.dish_id)
        if current is None or priority[row.value_type.value] < priority[current.value_type.value]:
            best[row.dish_id] = row

    expected = {
        field: sum((getattr(row, field) for row in best.values()), Decimal("0"))
        for field in NUTRIENT_FIELDS
    }
    actual = {item["code"]: item for item in body["latest"]}

    assert Decimal(actual["ENERGY"]["value"]) == expected["energy_kcal"]
    assert Decimal(actual["PROTEIN"]["value"]) == expected["protein_g"]
    # 同一道菜的三份结果条数一定多于菜品数，否则下面的断言就没在验任何东西
    assert len(rows) > len(best)


def test_days_parameter_is_validated(as_recorder: TestClient) -> None:
    assert as_recorder.get(f"{BASE}/trends", params={"days": 0}).status_code == 422
    assert as_recorder.get(f"{BASE}/trends", params={"days": 365}).status_code == 422


def test_menu_overview_has_today_and_tomorrow_three_meals(
    as_school_admin: TestClient,
) -> None:
    body = as_school_admin.get(f"{BASE}/menus").json()

    assert body["today"] == today_local().isoformat()
    assert body["tomorrow"] == (today_local() + timedelta(days=1)).isoformat()
    assert [day["day_label"] for day in body["days"]] == ["今天", "明天"]
    for day in body["days"]:
        assert [meal["meal_type"] for meal in day["meals"]] == [
            "BREAKFAST",
            "LUNCH",
            "DINNER",
        ]
    # 种子数据录过今天的采集，今天三餐应当标成实际供应
    assert all(meal["status"] == "ACTUAL" for meal in body["days"][0]["meals"])
    assert all(meal["diner_count"] for meal in body["days"][0]["meals"])


def test_menu_overview_hides_a_plan_that_was_not_adopted(as_recorder: TestClient) -> None:
    target = today_local() + timedelta(days=1)
    generated = as_recorder.post(
        "/api/v1/menu-plan/generate",
        params={"on_date": target.isoformat(), "meal_type": "LUNCH"},
    )
    assert generated.status_code == 200, generated.text

    body = as_recorder.get(f"{BASE}/menus").json()
    lunch = next(meal for meal in body["days"][1]["meals"] if meal["meal_type"] == "LUNCH")

    assert lunch["status"] == "NOT_PLANNED"
    assert lunch["dishes"] == []


def test_menu_overview_shows_tomorrows_adopted_plan(as_recorder: TestClient) -> None:
    """采纳（同步）之后，明天的菜单与份数要立刻出现在看板菜单页。"""
    target = today_local() + timedelta(days=1)
    generated = as_recorder.post(
        "/api/v1/menu-plan/generate",
        params={"on_date": target.isoformat(), "meal_type": "LUNCH"},
    )
    assert generated.status_code == 200, generated.text
    plan = generated.json()

    synced = as_recorder.post(
        "/api/v1/menu-plan/sync",
        params={
            "on_date": target.isoformat(),
            "meal_type": "LUNCH",
            "suggestion_id": plan["suggestion_id"],
        },
    )
    assert synced.status_code == 200, synced.text

    body = as_recorder.get(f"{BASE}/menus").json()
    lunch = next(meal for meal in body["days"][1]["meals"] if meal["meal_type"] == "LUNCH")

    assert lunch["status"] == "PLANNED"
    assert lunch["status_label"] == "计划供应"
    assert {dish["name"] for dish in lunch["dishes"]} == {
        dish["dish_name"] for dish in plan["dishes"]
    }
    assert all(dish["planned_servings"] for dish in lunch["dishes"])
    assert lunch["diner_count"] is None

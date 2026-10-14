"""管理端看板接口的行为约定。

重点：需要登录、聚合结果与手算一致、切换时间范围结果随之变化。
"""

from __future__ import annotations

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from app.modules.collection.models import DailyLog
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

BASE = "/api/v1/dashboard"


def test_dashboard_requires_login(client: TestClient) -> None:
    for path in ("summary", "trends", "per-capita", "compliance", "waste"):
        assert client.get(f"{BASE}/{path}").status_code == 401


def test_school_admin_can_view_dashboard(as_school_admin: TestClient) -> None:
    assert as_school_admin.get(f"{BASE}/summary").status_code == 200


def test_summary_average_salt_matches_manual_calculation(
    as_recorder: TestClient, db_session: Session
) -> None:
    """人均食盐是「各餐各自除以本餐人次再按天取平均」，这里独立算一遍核对。"""
    by_day: dict[object, list[DailyLog]] = defaultdict(list)
    for log in db_session.scalars(select(DailyLog)):
        by_day[log.date].append(log)
    per_day = [
        sum((log.salt_total_g / Decimal(log.diner_count) for log in logs), Decimal("0"))
        for logs in by_day.values()
        if logs
    ]
    expected = (sum(per_day) / Decimal(len(per_day))).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    # 演示历史是 8 周，因此显式按 8 周取，让统计窗口与库里的数据范围一致
    body = as_recorder.get(f"{BASE}/summary", params={"days": 56}).json()

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
    assert "理论值" in body["basis_note"]
    assert "实际投料量" in body["basis_note"]
    assert len(body["comparisons"]) == 4


def test_days_parameter_is_validated(as_recorder: TestClient) -> None:
    assert as_recorder.get(f"{BASE}/trends", params={"days": 0}).status_code == 422
    assert as_recorder.get(f"{BASE}/trends", params={"days": 365}).status_code == 422

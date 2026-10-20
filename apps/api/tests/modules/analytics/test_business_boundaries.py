from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

from app.core.config import get_settings
from app.modules.analytics import service
from app.modules.dish.models import Dish

from tests.helpers import today_local


def payload(ids, *, weight="10", meal="LUNCH"):
    return {
        "meal_type": meal,
        "diner_count": 100,
        "oil_total_g": "0",
        "salt_total_g": "0",
        "sugar_total_g": "0",
        "leftover_weight_g": weight,
        "dishes": [
            {"dish_id": dish_id, "servings_produced": "1", "leftover_weight_g": "999"}
            for dish_id in ids
        ],
    }


def test_waste_uses_meal_total_once_and_keeps_missing_distinct_from_zero(
    as_recorder, db_session, monkeypatch
):
    target = today_local() + timedelta(days=1900)
    ids = [row["id"] for row in as_recorder.get("/api/v1/dishes?page_size=100").json()["items"][:2]]
    monkeypatch.setattr(service, "_range", lambda days: (target, target))
    for weight in ("10", None, "0"):
        response = as_recorder.put(
            f"/api/v1/collection/logs/{target}", json=payload(ids, weight=weight)
        )
        assert response.status_code == 200, response.text
        db_session.expire_all()
        point = service.build_waste(db_session, days=1).points[0]
        if weight is None:
            assert point.leftover_weight_g is None and point.waste_ratio is None
        else:
            assert Decimal(point.leftover_weight_g) == Decimal(weight)
            expected = (Decimal(weight) / Decimal(point.produced_weight_g)).quantize(
                Decimal("0.0001")
            )
            assert Decimal(point.waste_ratio) == expected
    # 一餐有值、一餐缺测，不能把午餐的值冒充全日总重。
    assert (
        as_recorder.put(
            f"/api/v1/collection/logs/{target}", json=payload(ids, weight=None, meal="DINNER")
        ).status_code
        == 200
    )
    db_session.expire_all()
    assert service.build_waste(db_session, days=1).points[0].waste_ratio is None


def test_inactive_historical_dish_stays_selected_and_can_be_resaved(as_recorder, db_session):
    target = today_local() + timedelta(days=1901)
    dish_id = as_recorder.get("/api/v1/dishes?page_size=100").json()["items"][0]["id"]
    assert (
        as_recorder.put(f"/api/v1/collection/logs/{target}", json=payload([dish_id])).status_code
        == 200
    )
    dish = db_session.get(Dish, UUID(dish_id))
    dish.is_active = False
    db_session.commit()
    try:
        sheet = as_recorder.get(f"/api/v1/collection/logs/{target}").json()
        selected = [row["dish_id"] for row in sheet["dishes"] if row["selected"]]
        assert dish_id in selected
        response = as_recorder.put(f"/api/v1/collection/logs/{target}", json=payload(selected))
        assert response.status_code == 200, response.text
        assert response.json()["dish_count"] == 1
        empty_day = as_recorder.get(f"/api/v1/collection/logs/{target + timedelta(days=1)}").json()
        assert dish_id not in {row["dish_id"] for row in empty_day["dishes"]}
    finally:
        dish.is_active = True
        db_session.commit()


def test_unknown_denominators_remain_null(monkeypatch):
    target = today_local()
    monkeypatch.setattr(service, "_all_daily_actuals", lambda *args, **kwargs: ({target: {}}, []))
    compliance = service.build_compliance(None, days=7)
    assert compliance.points[0].total == 0
    assert compliance.points[0].rate is None
    assert compliance.overall_rate is None
    log = SimpleNamespace(
        date=target,
        diner_count=0,
        oil_total_g=Decimal(0),
        salt_total_g=Decimal(0),
        sugar_total_g=Decimal(0),
    )
    monkeypatch.setattr(service.repository, "load_daily_logs", lambda *args, **kwargs: [log])
    monkeypatch.setattr(service.repository, "load_active_standards", lambda *args: [])
    trend = service.build_trends(None, days=7).points[0]
    assert trend.salt_per_capita_g is None
    assert trend.salt_total_g == "0.00"


def test_registration_options_follow_server_setting(client, monkeypatch):
    for enabled in (False, True):
        monkeypatch.setattr(get_settings(), "allow_open_registration", enabled)
        response = client.get("/api/v1/auth/options")
        assert response.status_code == 200
        assert response.json() == {"registration_enabled": enabled}

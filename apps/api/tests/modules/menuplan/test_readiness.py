from datetime import timedelta

from app.modules.dish.models import Dish, RecipeItem
from app.modules.forecast.models import Forecast
from app.modules.ingredient.models import Ingredient
from app.modules.menuplan import readiness
from app.modules.recommendation.models import MenuSuggestion
from app.shared.enums import DishCategory, MealType
from sqlalchemy import func, select

from tests.helpers import today_local


def test_readiness_is_readonly_and_available_to_school(as_school_admin, db_session):
    before = [
        db_session.scalar(select(func.count()).select_from(model))
        for model in (Forecast, MenuSuggestion)
    ]
    response = as_school_admin.get(
        "/api/v1/menu-plan/readiness", params={"on_date": str(today_local() + timedelta(days=2))}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["available_count"] > 0
    assert body["predicted_count"] <= body["available_count"]
    assert body["history_end"] < body["on_date"]
    assert body["note"] and body["categories"]
    after = [
        db_session.scalar(select(func.count()).select_from(model))
        for model in (Forecast, MenuSuggestion)
    ]
    assert before == after


def test_other_meal_history_does_not_claim_readiness(as_recorder):
    response = as_recorder.get(
        "/api/v1/menu-plan/readiness",
        params={"on_date": str(today_local() + timedelta(days=2)), "meal_type": "DINNER"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "blocked"
    assert body["candidate_count"] == 0
    assert body["history_record_count"] == 0
    assert body["latest_diner_count"] is None
    assert any(row["code"] == "missing_category" for row in body["issues"])


def test_excluding_all_staples_identifies_specific_constraint(db_session):
    ids = frozenset(
        db_session.scalars(select(Dish.id).where(Dish.category == DishCategory.STAPLE)).all()
    )
    report = readiness.inspect(
        db_session,
        on_date=today_local() + timedelta(days=2),
        meal_type=MealType.LUNCH,
        excluded_dish_ids=ids,
    )
    assert report.state == "blocked"
    assert any(row.code == "missing_category" and "主食" in row.title for row in report.issues)


def test_missing_material_data_reports_real_entity_and_zero_is_not_missing(db_session):
    target = today_local() + timedelta(days=2)
    before = readiness.inspect(db_session, on_date=target, meal_type=MealType.LUNCH)
    material = db_session.scalar(
        select(Ingredient)
        .join(RecipeItem, RecipeItem.ingredient_id == Ingredient.id)
        .where(Ingredient.unit_price.is_not(None), Ingredient.protein_g.is_not(None))
        .order_by(Ingredient.name)
        .limit(1)
    )
    material.unit_price, material.protein_g = None, None
    db_session.flush()
    after = readiness.inspect(db_session, on_date=target, meal_type=MealType.LUNCH)
    assert after.missing_price_count > before.missing_price_count
    assert any(
        row.code == "missing_price" and row.entity_id == str(material.id) for row in after.issues
    )
    assert any(row.code == "missing_nutrition" and "蛋白质" in row.detail for row in after.issues)
    material.unit_price = material.protein_g = 0
    db_session.flush()
    zero = readiness.inspect(db_session, on_date=target, meal_type=MealType.LUNCH)
    assert not any(
        row.code == "missing_price" and row.entity_id == str(material.id) for row in zero.issues
    )


def test_readiness_requires_login_and_rejects_bad_exclusions(client):
    params = {"on_date": str(today_local())}
    assert client.get("/api/v1/menu-plan/readiness", params=params).status_code == 401
    client.post("/api/v1/auth/login", json={"username": "recorder", "password": "canteen@2026"})
    assert (
        client.get(
            "/api/v1/menu-plan/readiness", params={**params, "excluded_dish_ids": "bad-id"}
        ).status_code
        == 422
    )

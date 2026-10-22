from datetime import timedelta

from app.modules.collection.models import DailyLog, DailyLogItem
from app.modules.dish.models import Dish, RecipeItem
from app.modules.forecast.models import Forecast
from app.modules.ingredient.models import Ingredient
from app.modules.menuplan import readiness
from app.modules.menuplan import service as menuplan_service
from app.modules.recommendation import service as recommendation_service
from app.modules.recommendation.models import MenuSuggestion
from app.shared.enums import DishCategory, MealType
from sqlalchemy import delete, func, select

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
    assert body["predicted_diner_count"] > 0
    assert body["diner_count_lower"] <= body["predicted_diner_count"] <= body["diner_count_upper"]
    assert body["diner_count_basis"] and body["diner_count_basis_label"]
    assert body["history_end"] < body["on_date"]
    assert body["note"] and body["categories"]
    after = [
        db_session.scalar(select(func.count()).select_from(model))
        for model in (Forecast, MenuSuggestion)
    ]
    assert before == after


def test_other_meal_history_does_not_claim_readiness(db_session):
    """别的餐次的历史不能算成本餐次的准备度。

    种子现在三餐都有历史，所以要**先把晚餐历史清空**再问晚餐——
    否则「午餐用过的菜」会被当成晚餐也排过，准备度虚高成 ready。

    这里走 `db_session` 直接调 `inspect`，而不是走接口：同一条会话里看得见
    未提交的删除，走接口得先提交才生效，那会把测试数据留在库里。
    """
    dinner_log_ids = list(
        db_session.scalars(select(DailyLog.id).where(DailyLog.meal_type == MealType.DINNER))
    )
    if dinner_log_ids:
        db_session.execute(
            delete(DailyLogItem).where(DailyLogItem.daily_log_id.in_(dinner_log_ids))
        )
        db_session.execute(delete(DailyLog).where(DailyLog.id.in_(dinner_log_ids)))
        db_session.flush()

    report = readiness.inspect(
        db_session, on_date=today_local() + timedelta(days=2), meal_type=MealType.DINNER
    )

    assert report.state == "blocked"
    assert report.candidate_count == 0
    assert report.history_record_count == 0
    assert report.latest_diner_count is None
    assert report.predicted_diner_count is None
    assert any(row.code == "missing_category" for row in report.issues)


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


def test_fixed_breakfast_readiness_matches_generation_after_previous_supply(db_session):
    target = today_local() + timedelta(days=1)
    report = readiness.inspect(db_session, on_date=target, meal_type=MealType.BREAKFAST)
    assert report.candidate_count > 0
    assert report.available_count == report.candidate_count
    assert report.state != "blocked"
    plan = menuplan_service.build_menu_plan(
        db_session, on_date=target, meal_type=MealType.BREAKFAST
    )
    assert len(plan.dishes) == report.available_count


def test_breakfast_explicit_exclusion_matches_fixed_plan(db_session):
    target = today_local() + timedelta(days=2)
    candidates = recommendation_service.candidate_dish_ids(
        db_session, on_date=target, meal_type=MealType.BREAKFAST
    )
    excluded = frozenset(candidates[:1])
    report = readiness.inspect(
        db_session, on_date=target, meal_type=MealType.BREAKFAST, excluded_dish_ids=excluded
    )
    plan = menuplan_service.build_menu_plan(
        db_session, on_date=target, meal_type=MealType.BREAKFAST, excluded_dish_ids=excluded
    )
    assert not ({str(item) for item in excluded} & {dish.dish_id for dish in plan.dishes})
    assert len(plan.dishes) == report.available_count


def test_breakfast_fixed_set_does_not_require_lunch_categories(db_session):
    target = today_local() + timedelta(days=2)
    candidates = recommendation_service.candidate_dish_ids(
        db_session, on_date=target, meal_type=MealType.BREAKFAST
    )
    staple = db_session.scalar(
        select(Dish.id).where(Dish.id.in_(candidates), Dish.category == DishCategory.STAPLE)
    )
    assert staple is not None
    excluded = frozenset(set(candidates) - {staple})
    report = readiness.inspect(
        db_session, on_date=target, meal_type=MealType.BREAKFAST, excluded_dish_ids=excluded
    )
    assert report.available_count == 1
    assert report.state != "blocked"
    empty = readiness.inspect(
        db_session,
        on_date=target,
        meal_type=MealType.BREAKFAST,
        excluded_dish_ids=frozenset(candidates),
    )
    assert empty.state == "blocked"

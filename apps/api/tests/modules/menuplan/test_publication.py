"""在独立测试库验证真实计算/发布。不能在用户开发库运行本文件。"""

from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from app.db import seed as seed_module
from app.db.session import get_session_factory
from app.modules.audit.models import AuditLog
from app.modules.dish.models import Dish, RecipeItem
from app.modules.ingredient.models import Ingredient
from app.modules.menu.models import MenuDayItem
from app.modules.nutrition import service as nutrition_service
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tests.conftest import _baseline_ids, _delete_rows_outside_baseline
from tests.helpers import today_local

BASE = "/api/v1/menu-plan"


@pytest.fixture(scope="module", autouse=True)
def restore_publication_examples(prepared_database):
    """本模块会发布未来菜单，结束时清理，避免影响其他模块的连续两日排重。"""
    with get_session_factory()() as session:
        baseline = _baseline_ids(session)
    yield
    with get_session_factory()() as session:
        _delete_rows_outside_baseline(session, baseline)
        seed_module.run(session)
        nutrition_service.compute_recent_days(session, days=seed_module.HISTORY_DAYS)


def generate(client, offset=2, **constraints):
    response = client.post(
        f"{BASE}/generate",
        params={"on_date": str(today_local() + timedelta(days=offset)), "diner_count": 800},
        json=constraints,
    )
    assert response.status_code == 200, response.text
    return response.json()


def confirm(client, plan, **overrides):
    return client.post(
        f"{BASE}/{plan['suggestion_id']}/publish",
        json={
            "snapshot_token": plan["snapshot_token"],
            "expected_menu_token": plan["expected_menu_token"],
            **overrides,
        },
    )


def test_publish_writes_menu_nutrition_and_one_audit_idempotently(
    as_recorder: TestClient, db_session: Session
):
    plan = generate(as_recorder, offset=3)
    response = confirm(as_recorder, plan)
    assert response.status_code == 200, response.text
    receipt = response.json()
    menu_id = UUID(receipt["menu_day_id"])
    items = db_session.scalars(select(MenuDayItem).where(MenuDayItem.menu_day_id == menu_id)).all()
    assert {str(row.dish_id) for row in items} == {row["dish_id"] for row in plan["dishes"]}
    assert all(row.planned_servings > 0 for row in items)
    repeated = confirm(as_recorder, plan)
    assert repeated.status_code == 200
    assert repeated.json()["already_published"]
    assert (
        db_session.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == str(menu_id))
        )
        == 1
    )
    board = as_recorder.get("/api/v1/public/board/today", params={"on_date": plan["date"]})
    assert board.status_code == 200, board.text
    assert {str(row["dish_id"]) for row in board.json()["dishes"]} == {
        row["dish_id"] for row in plan["dishes"]
    }


def test_stale_plan_cannot_replace_new_menu(as_recorder: TestClient):
    old, fresh = generate(as_recorder, offset=12), generate(as_recorder, offset=12)
    assert confirm(as_recorder, fresh).status_code == 200
    response = confirm(as_recorder, old)
    assert response.status_code == 409, response.text
    assert "修改" in response.json()["message"]


def test_calculation_upgrade_requires_recompute_but_keeps_old_receipt(as_recorder, monkeypatch):
    from app.modules.menuplan import publication

    draft = generate(as_recorder, offset=34)
    published = generate(as_recorder, offset=35)
    assert confirm(as_recorder, published).status_code == 200
    monkeypatch.setattr(publication, "CALCULATION_VERSION", "next-calculation-version")
    rejected = confirm(as_recorder, draft)
    assert rejected.status_code == 409 and "计算规则" in rejected.json()["message"]
    repeated = confirm(as_recorder, published)
    assert repeated.status_code == 200 and repeated.json()["already_published"]


def test_tampered_token_and_unknown_exclusion_rejected(as_recorder: TestClient):
    plan = generate(as_recorder, offset=5)
    assert confirm(as_recorder, plan, snapshot_token="0" * 64).status_code == 409
    bad = as_recorder.post(
        f"{BASE}/generate",
        params={"on_date": plan["date"]},
        json={"excluded_dish_ids": [str(uuid4())]},
    )
    assert bad.status_code == 422


def test_existing_new_dish_can_be_excluded_without_inventing_history(as_recorder):
    created = as_recorder.post(
        "/api/v1/dishes",
        json={
            "name": f"未供应测试菜{uuid4().hex[:6]}",
            "category": "VEGETABLE",
            "cooking_method": "STEAM",
            "standard_serving_g": "100",
            "servings_per_pot": "100",
            "allergens": [],
        },
    )
    assert created.status_code == 201, created.text
    plan = generate(as_recorder, offset=43, excluded_dish_ids=[created.json()["id"]])
    assert all(row["dish_id"] != created.json()["id"] for row in plan["dishes"])


def test_school_admin_cannot_publish(as_recorder: TestClient, as_school_admin: TestClient):
    # 两个夹具可能共享 client，因此显式重新登录。
    as_recorder.post(
        "/api/v1/auth/login", json={"username": "recorder", "password": "canteen@2026"}
    )
    plan = generate(as_recorder, offset=6)
    as_school_admin.post(
        "/api/v1/auth/login", json={"username": "school", "password": "canteen@2026"}
    )
    assert confirm(as_school_admin, plan).status_code == 403


def test_recipe_change_prevents_publish(as_recorder: TestClient, db_session: Session):
    plan = generate(as_recorder, offset=7)
    dish = db_session.get(Dish, UUID(plan["dishes"][0]["dish_id"]))
    dish.recipe_version += 1
    db_session.commit()
    response = confirm(as_recorder, plan)
    assert response.status_code == 409, response.text
    dish.recipe_version -= 1
    db_session.commit()


def test_diner_change_scales_purchase_and_budget(as_recorder: TestClient):
    target = str(today_local() + timedelta(days=8))
    plans = [
        as_recorder.post(
            f"{BASE}/generate",
            params={"on_date": target, "diner_count": count},
            json={"budget_per_person": "8"},
        ).json()
        for count in (600, 1200)
    ]
    a, b = plans
    assert a["budget"] == "4800.00" and b["budget"] == "9600.00"
    assert [row["dish_id"] for row in a["dishes"]] == [row["dish_id"] for row in b["dishes"]]
    for one, two in zip(a["dishes"], b["dishes"], strict=True):
        assert abs(
            Decimal(two["predicted_servings"]) - Decimal(one["predicted_servings"]) * 2
        ) <= Decimal("0.02")
    assert abs(Decimal(b["total_cost"]) - Decimal(a["total_cost"]) * 2) < 1


def test_no_solution_has_actionable_error(as_recorder: TestClient):
    response = as_recorder.post(
        f"{BASE}/generate",
        params={"on_date": str(today_local() + timedelta(days=9))},
        json={"budget_per_person": "0.01"},
    )
    assert response.status_code == 422
    assert response.json()["details"]["conflicts"]


def test_price_change_invalidates_snapshot(as_recorder: TestClient, db_session: Session):
    plan = generate(as_recorder, offset=20)
    ingredient = db_session.scalar(
        select(Ingredient)
        .join(RecipeItem, RecipeItem.ingredient_id == Ingredient.id)
        .where(RecipeItem.dish_id == UUID(plan["dishes"][0]["dish_id"]))
    )
    old = ingredient.unit_price
    try:
        ingredient.unit_price = (old or Decimal("1")) + Decimal("1")
        db_session.commit()
        response = confirm(as_recorder, plan)
        assert response.status_code == 409, response.text
        assert "单价" in response.json()["message"]
    finally:
        ingredient.unit_price = old
        db_session.commit()


def test_missing_price_in_an_excluded_dish_does_not_make_the_plan_cost_incomplete(
    as_recorder, db_session
):
    from sqlalchemy import distinct

    unique_ingredient = db_session.scalar(
        select(RecipeItem.ingredient_id)
        .group_by(RecipeItem.ingredient_id)
        .having(func.count(distinct(RecipeItem.dish_id)) == 1)
        .order_by(RecipeItem.ingredient_id)
        .limit(1)
    )
    ingredient = db_session.get(Ingredient, unique_ingredient)
    excluded = db_session.scalar(
        select(RecipeItem.dish_id).where(RecipeItem.ingredient_id == unique_ingredient)
    )
    original = ingredient.unit_price
    try:
        ingredient.unit_price = None
        db_session.commit()
        plan = generate(as_recorder, offset=42, excluded_dish_ids=[str(excluded)])
        assert all(row["dish_id"] != str(excluded) for row in plan["dishes"])
        assert all(row["unit_price"] is not None for row in plan["requirements"])
        assert plan["missing_price_warning"] is None
    finally:
        ingredient.unit_price = original
        db_session.commit()


def test_actual_collection_is_not_overwritten(as_recorder: TestClient):
    plan = generate(as_recorder, offset=22)
    saved = as_recorder.put(
        f"/api/v1/collection/logs/{plan['date']}",
        json={
            "meal_type": "LUNCH",
            "diner_count": 800,
            "dishes": [{"dish_id": plan["dishes"][0]["dish_id"], "servings_produced": "100"}],
        },
    )
    assert saved.status_code == 200, saved.text
    # 在实际数据落库后重算，菜单版本相符也必须拒绝计划覆盖。
    fresh = generate(as_recorder, offset=22)
    response = confirm(as_recorder, fresh)
    assert response.status_code == 409, response.text
    assert "实际采集" in response.json()["message"]


def test_explicit_exclusion_really_changes_menu(as_recorder: TestClient):
    plan = generate(as_recorder, offset=24)
    excluded = plan["dishes"][0]["dish_id"]
    changed = generate(as_recorder, offset=24, excluded_dish_ids=[excluded])
    assert excluded not in {row["dish_id"] for row in changed["dishes"]}
    assert changed["requested_excluded_dish_ids"] == [excluded]
    assert any("本次要求" in row["text"] for row in changed["reasons"])


def test_published_decision_cannot_be_rewritten(as_recorder: TestClient):
    plan = generate(as_recorder, offset=26)
    assert confirm(as_recorder, plan).status_code == 200
    response = as_recorder.post(
        f"/api/v1/recommendation/{plan['suggestion_id']}/decide",
        json={"status": "REJECTED", "reason": "不应覆盖确认记录"},
    )
    assert response.status_code == 409


def test_concurrent_publish_has_one_effect(as_recorder: TestClient, db_session: Session):
    from concurrent.futures import ThreadPoolExecutor

    plan = generate(as_recorder, offset=28)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: confirm(as_recorder, plan), range(2)))
    assert all(response.status_code == 200 for response in responses), [
        response.text for response in responses
    ]
    assert sum(not response.json()["already_published"] for response in responses) == 1
    menu_id = responses[0].json()["menu_day_id"]
    assert (
        db_session.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == menu_id)
        )
        == 1
    )


def test_change_during_generation_cannot_be_blessed_as_current_snapshot(
    as_recorder: TestClient, monkeypatch
):
    from app.modules.menuplan import publication

    original = publication.save_snapshot
    changed = {}

    def change_then_save(session, plan, before):
        item = session.scalar(
            select(RecipeItem).where(RecipeItem.dish_id == UUID(plan.dishes[0].dish_id))
        )
        old_reference = session.get(Ingredient, item.ingredient_id)
        with get_session_factory()() as other:
            row = other.get(Ingredient, item.ingredient_id)
            changed["id"], changed["old"] = row.id, row.unit_price
            row.unit_price = (row.unit_price or Decimal("0")) + 1
            other.commit()
        assert old_reference.unit_price == changed["old"]
        return original(session, plan, before)

    monkeypatch.setattr(publication, "save_snapshot", change_then_save)
    try:
        response = as_recorder.post(
            f"{BASE}/generate",
            params={"on_date": str(today_local() + timedelta(days=18)), "diner_count": 800},
        )
        assert response.status_code == 409, response.text
        assert "计算期间" in response.json()["message"]
    finally:
        if changed:
            with get_session_factory()() as other:
                other.get(Ingredient, changed["id"]).unit_price = changed["old"]
                other.commit()

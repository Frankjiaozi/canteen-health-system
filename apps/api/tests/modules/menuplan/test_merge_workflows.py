"""两套助手、单日/批量同步与实际采集共用业务保护。只在隔离测试库运行。"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from app.core.config import get_settings
from app.core.errors import AppError
from app.db import seed
from app.db.session import get_session_factory
from app.modules.assistant import repository, tools
from app.modules.auth.repository import get_by_username
from app.modules.auth.service import to_auth_user
from app.modules.dish.models import Dish, RecipeItem
from app.modules.ingredient.models import Ingredient
from app.modules.menu import service as menu_service
from app.modules.menu.models import MenuDay, MenuDayItem
from app.modules.menuplan import publication
from app.modules.nutrition import service as nutrition_service
from app.modules.recommendation.models import MenuSuggestion
from app.shared.enums import MealType
from sqlalchemy import select

from tests.conftest import _baseline_ids, _delete_rows_outside_baseline
from tests.helpers import today_local


@pytest.fixture(scope="module", autouse=True)
def restore_merge_examples(prepared_database):
    with get_session_factory()() as session:
        baseline = _baseline_ids(session)
    yield
    with get_session_factory()() as session:
        _delete_rows_outside_baseline(session, baseline)
        seed.run(session)
        nutrition_service.compute_recent_days(session, days=seed.HISTORY_DAYS)


def plan(client, offset):
    target = today_local() + timedelta(days=offset)
    response = client.post(
        "/api/v1/menu-plan/generate",
        params={"on_date": str(target), "meal_type": "LUNCH", "diner_count": 1000},
    )
    assert response.status_code == 200, response.text
    return target, response.json()


def actor(session):
    return to_auth_user(get_by_username(session, "recorder"))


def sync_draft(session, target):
    return tools.sync_menu_plan_draft(session, on_date=str(target), meal_type="LUNCH")


@pytest.mark.parametrize("entry", ["single", "batch", "assistant"])
def test_all_sync_entries_reject_a_price_change(as_recorder, db_session, entry):
    target, result = plan(as_recorder, 10)
    draft = sync_draft(db_session, target)
    recipe = db_session.scalar(
        select(RecipeItem).where(RecipeItem.dish_id == UUID(result["dishes"][0]["dish_id"]))
    )
    ingredient = db_session.get(Ingredient, recipe.ingredient_id)
    original = ingredient.unit_price
    ingredient.unit_price = (original or Decimal(0)) + 1
    db_session.commit()
    try:
        if entry == "assistant":
            with pytest.raises(AppError, match="单价"):
                tools.sync_menu_plan_execute(db_session, draft["payload"], actor=actor(db_session))
        elif entry == "batch":
            response = as_recorder.post(
                "/api/v1/menu-plan/batch/sync",
                params={"start_date": str(target), "end_date": str(target)},
            )
            assert response.status_code == 200, response.text
            assert response.json()["failed"] == 1
            assert "单价" in response.json()["rows"][0]["reason"]
        else:
            response = as_recorder.post(
                "/api/v1/menu-plan/sync",
                params={"on_date": str(target), "suggestion_id": result["suggestion_id"]},
            )
            assert response.status_code == 409 and "单价" in response.json()["message"]
        assert db_session.scalar(select(MenuDay.id).where(MenuDay.date == target)) is None
    finally:
        db_session.rollback()
        ingredient = db_session.get(Ingredient, recipe.ingredient_id)
        ingredient.unit_price = original
        db_session.commit()


@pytest.mark.parametrize("had_menu", [False, True])
def test_sync_undo_restores_full_original_and_invalidates_receipt(
    as_recorder, db_session, had_menu
):
    target = today_local() + timedelta(days=12)
    if had_menu:
        dish = db_session.scalar(select(Dish).where(Dish.is_active.is_(True)))
        menu_id = menu_service.plan_menu_day(
            db_session,
            on_date=target,
            meal_type=MealType.LUNCH,
            dishes=[menu_service.PlannedDish(dish_id=dish.id)],
            created_by=actor(db_session).id,
        )
        menu = db_session.get(MenuDay, menu_id)
        menu.note, menu.rotation_name = "原菜单备注", "原轮换"
        item = db_session.scalar(select(MenuDayItem).where(MenuDayItem.menu_day_id == menu_id))
        item.is_substituted, item.substitution_note = True, "原替换说明"
        db_session.commit()
    before = publication.meal_state(db_session, on_date=target, meal_type=MealType.LUNCH)
    _, result = plan(as_recorder, 12)
    outcome = tools.sync_menu_plan_execute(
        db_session, sync_draft(db_session, target)["payload"], actor=actor(db_session)
    )
    assert len(outcome.undo) == 1
    tools.restore_menu_day_execute(db_session, outcome.undo[0].payload, actor=actor(db_session))
    after = publication.meal_state(db_session, on_date=target, meal_type=MealType.LUNCH)
    if had_menu:
        assert after["note"] == "原菜单备注" and after["rotation_name"] == "原轮换"
        assert [(row[0], row[1], row[3], row[4]) for row in after["items"]] == [
            (row[0], row[1], row[3], row[4]) for row in before["items"]
        ]
        assert after["items"][0][1] == "None"
    else:
        assert after == {"menu": None}
    saved = db_session.get(MenuSuggestion, UUID(result["suggestion_id"]))
    assert saved.nutrition_gap["publication"] and saved.nutrition_gap["publication_revoked"]
    response = as_recorder.post(
        f"/api/v1/menu-plan/{result['suggestion_id']}/publish",
        json={
            "snapshot_token": result["snapshot_token"],
            "expected_menu_token": result["expected_menu_token"],
        },
    )
    assert response.status_code == 409 and "撤回" in response.json()["message"]
    batch = as_recorder.post(
        "/api/v1/menu-plan/batch/sync", params={"start_date": str(target), "end_date": str(target)}
    )
    assert batch.status_code == 200 and batch.json()["failed"] == 1
    assert "撤回" in batch.json()["rows"][0]["reason"]


def test_menu_draft_and_undo_cannot_overwrite_a_later_publish(as_recorder, db_session):
    target, first = plan(as_recorder, 14)
    names = [row["dish_name"] for row in first["dishes"][:2]]
    pending = tools.set_menu_day_draft(
        db_session, on_date=str(target), meal_type="LUNCH", dish_names=names
    )
    outcome = tools.set_menu_day_execute(db_session, pending["payload"], actor=actor(db_session))
    stale = as_recorder.post(
        "/api/v1/menu-plan/sync",
        params={"on_date": str(target), "suggestion_id": first["suggestion_id"]},
    )
    assert stale.status_code == 409 and "修改" in stale.json()["message"]
    _, second = plan(as_recorder, 14)
    published = as_recorder.post(
        f"/api/v1/menu-plan/{second['suggestion_id']}/publish",
        json={
            "snapshot_token": second["snapshot_token"],
            "expected_menu_token": second["expected_menu_token"],
        },
    )
    assert published.status_code == 200, published.text
    with pytest.raises(AppError, match="修改"):
        tools.restore_menu_day_execute(db_session, outcome.undo[0].payload, actor=actor(db_session))
    with pytest.raises(AppError, match="变化"):
        tools.set_menu_day_execute(db_session, pending["payload"], actor=actor(db_session))


def test_actual_collection_blocks_menu_undo(as_recorder, db_session):
    target, result = plan(as_recorder, 16)
    outcome = tools.sync_menu_plan_execute(
        db_session, sync_draft(db_session, target)["payload"], actor=actor(db_session)
    )
    saved = as_recorder.put(
        f"/api/v1/collection/logs/{target}",
        json={
            "meal_type": "LUNCH",
            "diner_count": 1000,
            "oil_total_g": "1000",
            "salt_total_g": "500",
            "sugar_total_g": "100",
            "dishes": [{"dish_id": result["dishes"][0]["dish_id"], "servings_produced": "10"}],
        },
    )
    assert saved.status_code == 200, saved.text
    with pytest.raises(AppError):
        tools.restore_menu_day_execute(db_session, outcome.undo[0].payload, actor=actor(db_session))
    assert (
        as_recorder.get(f"/api/v1/collection/logs/{target}", params={"meal_type": "LUNCH"}).json()[
            "saved"
        ]
        is True
    )


def test_failed_menu_undo_rolls_back_menu_receipt_and_proposal(
    as_recorder, db_session, monkeypatch
):
    target, result = plan(as_recorder, 18)
    who = actor(db_session)
    draft = sync_draft(db_session, target)
    conversation = repository.create_conversation(
        db_session,
        user_id=who.id,
        user_name=who.display_name,
        title="整合撤回验证",
        now=datetime.now(get_settings().timezone),
    )
    proposal = repository.create_proposal(
        db_session,
        conversation_id=conversation.id,
        tool_name="sync_menu_plan",
        title=draft["title"],
        summary=draft["summary"],
        payload=draft["payload"],
        preview=draft["preview"],
        created_by=who.id,
        created_by_name=who.display_name,
    )
    db_session.commit()
    confirmed = as_recorder.post(f"/api/v1/assistant/proposals/{proposal.id}/confirm")
    assert confirmed.status_code == 200 and confirmed.json()["status"] == "CONFIRMED"
    before = publication.meal_state(db_session, on_date=target, meal_type=MealType.LUNCH)

    def broken(*args, **kwargs):
        raise RuntimeError("injected undo computation failure")

    monkeypatch.setattr(publication.nutrition_service, "compute_menu_day", broken)
    response = as_recorder.post(f"/api/v1/assistant/proposals/{proposal.id}/revoke")
    assert response.status_code == 500
    db_session.expire_all()
    assert publication.meal_state(db_session, on_date=target, meal_type=MealType.LUNCH) == before
    assert not db_session.get(MenuSuggestion, UUID(result["suggestion_id"])).nutrition_gap.get(
        "publication_revoked"
    )
    assert repository.get_proposal(db_session, proposal.id).status.value == "CONFIRMED"


def test_same_menu_card_concurrent_confirmation_keeps_original_undo(as_recorder, db_session):
    target, _ = plan(as_recorder, 20)
    who = actor(db_session)
    draft = sync_draft(db_session, target)
    conversation = repository.create_conversation(
        db_session,
        user_id=who.id,
        user_name=who.display_name,
        title="同卡并发验证",
        now=datetime.now(get_settings().timezone),
    )
    proposal = repository.create_proposal(
        db_session,
        conversation_id=conversation.id,
        tool_name="sync_menu_plan",
        title=draft["title"],
        summary=draft["summary"],
        payload=draft["payload"],
        preview=draft["preview"],
        created_by=who.id,
        created_by_name=who.display_name,
    )
    db_session.commit()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(as_recorder.post, f"/api/v1/assistant/proposals/{proposal.id}/confirm")
            for _ in range(2)
        ]
        responses = [future.result() for future in futures]
    assert sorted(response.status_code for response in responses) == [200, 422]
    db_session.expire_all()
    saved = repository.get_proposal(db_session, proposal.id)
    assert len(saved.undo) == 1 and saved.undo[0]["payload"]["before"] == {"menu": None}
    revoked = as_recorder.post(f"/api/v1/assistant/proposals/{proposal.id}/revoke")
    assert revoked.status_code == 200 and revoked.json()["status"] == "REVERTED"
    assert publication.meal_state(db_session, on_date=target, meal_type=MealType.LUNCH) == {
        "menu": None
    }


def test_sync_parallel_calls_return_the_same_publication(as_recorder):
    target, result = plan(as_recorder, 22)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = [
            future.result()
            for future in [
                pool.submit(
                    as_recorder.post,
                    "/api/v1/menu-plan/sync",
                    params={"on_date": str(target), "suggestion_id": result["suggestion_id"]},
                )
                for _ in range(2)
            ]
        ]
    assert [response.status_code for response in responses] == [200, 200], [
        r.text for r in responses
    ]
    assert responses[0].json()["suggestion_id"] == responses[1].json()["suggestion_id"]


def test_preloaded_suggestion_cannot_hide_a_later_rejection(as_recorder, db_session):
    from app.modules.recommendation import service as recommendation_service
    from app.modules.recommendation.schemas import DecideRequest
    from app.shared.enums import SuggestionStatus

    _target, result = plan(as_recorder, 24)
    sid = UUID(result["suggestion_id"])
    old = db_session.get(MenuSuggestion, sid)
    assert old.status is SuggestionStatus.PENDING
    with get_session_factory()() as other:
        recommendation_service.decide(
            other,
            suggestion_id=sid,
            payload=DecideRequest(status=SuggestionStatus.REJECTED, reason="人工否决"),
            actor_id=actor(other).id,
        )
    with pytest.raises(AppError, match="否决"):
        publication.publish(
            db_session,
            suggestion_id=sid,
            payload=publication.PublishPlanRequest(
                snapshot_token=result["snapshot_token"],
                expected_menu_token=result["expected_menu_token"],
            ),
            actor=actor(db_session),
        )


def test_collection_undo_cannot_remove_later_actual_changes(as_recorder, db_session):
    target = today_local() + timedelta(days=26)
    dish = db_session.scalar(select(Dish).where(Dish.is_active.is_(True)))
    who = actor(db_session)
    draft = tools.save_collection_draft(
        db_session,
        on_date=str(target),
        meal_type="LUNCH",
        diner_count=1000,
        dishes=[{"dish_name": dish.name, "servings": "100"}],
    )
    outcome = tools.save_collection_execute(db_session, draft["payload"], actor=who)
    updated = as_recorder.put(
        f"/api/v1/collection/logs/{target}",
        json={
            "meal_type": "LUNCH",
            "diner_count": 1200,
            "oil_total_g": "1000",
            "salt_total_g": "500",
            "sugar_total_g": "100",
            "dishes": [{"dish_id": str(dish.id), "servings_produced": "200"}],
        },
    )
    assert updated.status_code == 200, updated.text
    with pytest.raises(AppError, match="又被改过"):
        tools.restore_collection_execute(db_session, outcome.undo[0].payload, actor=who)
    current = as_recorder.get(
        f"/api/v1/collection/logs/{target}", params={"meal_type": "LUNCH"}
    ).json()
    assert current["saved"] and current["diner_count"] == 1200

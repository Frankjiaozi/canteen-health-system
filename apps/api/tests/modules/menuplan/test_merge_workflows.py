"""单日 / 批量同步与实际采集共用同一套发布保护。只在隔离测试库运行。

这个文件原本还覆盖「业务侧 AI 助手」那套确认卡与撤回——那个助手已经下线，
只保留知味膳食助手；相关用例搬走或并入 `test_publication.py`：

| 原来的用例 | 现在在哪 |
| --- | --- |
| 撤回要把菜单恢复成发布前的样子 | 这里（改走 `POST /menu-plan/{id}/undo`） |
| 发布后菜单被改过 / 已录采集就不能撤 | `test_publication.py` |
| 助手卡片并发确认、proposal 状态回滚 | 随助手一起删除——那套机制不存在了 |
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from app.core.errors import AppError
from app.db import seed
from app.db.session import get_session_factory
from app.modules.audit.models import AuditLog  # noqa: F401  （保留：发布与撤回都会写审计）
from app.modules.auth.repository import get_by_username
from app.modules.auth.service import to_auth_user
from app.modules.dish.models import Dish, RecipeItem
from app.modules.ingredient.models import Ingredient
from app.modules.menu import service as menu_service
from app.modules.menu.models import MenuDay, MenuDayItem
from app.modules.menuplan import publication
from app.modules.nutrition import service as nutrition_service
from app.modules.recommendation.models import MenuSuggestion
from app.shared.enums import MealType, SuggestionStatus
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


def test_batch_import_keeps_reviewed_id_when_a_newer_plan_exists(as_recorder, db_session):
    target, reviewed = plan(as_recorder, 120)
    _, newer = plan(as_recorder, 120)
    assert reviewed["suggestion_id"] != newer["suggestion_id"]
    response = as_recorder.post(
        "/api/v1/menu-plan/batch/sync",
        params={"start_date": str(target), "end_date": str(target)},
        json={"suggestion_ids": {str(target): reviewed["suggestion_id"]}},
    )
    assert response.status_code == 200, response.text
    row = response.json()["rows"][0]
    assert row["status"] == "IMPORTED"
    assert row["suggestion_id"] == reviewed["suggestion_id"]
    db_session.expire_all()
    stored = db_session.get(MenuSuggestion, UUID(newer["suggestion_id"]))
    assert not (stored.nutrition_gap or {}).get("publication")
    assert (
        as_recorder.post(
            "/api/v1/menu-plan/batch/sync",
            params={"start_date": str(target), "end_date": str(target)},
        ).status_code
        == 422
    )


def test_school_can_read_saved_procurement_snapshot(as_recorder):
    target, saved = plan(as_recorder, 121)
    from tests.conftest import login_as

    login_as(as_recorder, "school")
    response = as_recorder.get("/api/v1/menu-plan/history", params={"on_date": str(target)})
    assert response.status_code == 200, response.text
    stored = next(
        item["plan"]
        for item in response.json()
        if item["plan"]["suggestion_id"] == saved["suggestion_id"]
    )
    assert stored["requirements"] == saved["requirements"]
    assert stored["total_cost"] == saved["total_cost"]


def actor(session):
    return to_auth_user(get_by_username(session, "recorder"))


def publish(client, result):
    return client.post(
        f"/api/v1/menu-plan/{result['suggestion_id']}/publish",
        json={
            "snapshot_token": result["snapshot_token"],
            "expected_menu_token": result["expected_menu_token"],
        },
    )


def undo(client, result):
    return client.post(f"/api/v1/menu-plan/{result['suggestion_id']}/undo")


@pytest.mark.parametrize("entry", ["single", "batch"])
def test_all_sync_entries_reject_a_price_change(as_recorder, db_session, entry):
    """两个写入口都不能拿「单价已经变了」的快照去发布。"""
    target, result = plan(as_recorder, 10)
    recipe = db_session.scalar(
        select(RecipeItem).where(RecipeItem.dish_id == UUID(result["dishes"][0]["dish_id"]))
    )
    ingredient = db_session.get(Ingredient, recipe.ingredient_id)
    original = ingredient.unit_price
    ingredient.unit_price = (original or Decimal(0)) + 1
    db_session.commit()
    try:
        if entry == "batch":
            response = as_recorder.post(
                "/api/v1/menu-plan/batch/sync",
                json={"suggestion_ids": {str(target): result["suggestion_id"]}},
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
def test_undo_restores_full_original_and_invalidates_receipt(as_recorder, db_session, had_menu):
    """撤回要把菜单**整份**恢复原样：备注、轮换名、替换标记、空份数都不能丢。"""
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
    assert publish(as_recorder, result).status_code == 200
    assert undo(as_recorder, result).status_code == 200

    db_session.expire_all()
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
    assert saved is not None
    assert saved.nutrition_gap["publication"] and saved.nutrition_gap["publication_revoked"]
    # 撤回过的方案不能再发布，也不能被批量导入拿走
    again = publish(as_recorder, result)
    assert again.status_code == 409 and "撤回" in again.json()["message"]
    batch = as_recorder.post(
        "/api/v1/menu-plan/batch/sync",
        params={"start_date": str(target), "end_date": str(target)},
        json={"suggestion_ids": {str(target): result["suggestion_id"]}},
    )
    assert batch.status_code == 200 and batch.json()["failed"] == 1
    assert "撤回" in batch.json()["rows"][0]["reason"]


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
    """已经拿到手的方案被别人否决之后，发布必须失败，而不是照着旧副本写进菜单。"""
    from app.modules.recommendation import service as recommendation_service
    from app.modules.recommendation.schemas import DecideRequest

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

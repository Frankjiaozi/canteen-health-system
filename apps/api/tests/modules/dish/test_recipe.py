"""配方维护：整体替换、版本递增、留痕，以及保存后自动重算营养。"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from uuid import uuid4

import pytest
from app.db.session import get_session_factory
from app.modules.audit.models import AuditLog
from app.modules.dish.models import Dish, RecipeItem, RecipeSeasoning
from app.modules.nutrition.models import DishNutrition
from app.shared.enums import AuditAction, NutrientCaliber, NutritionValueType
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from tests.helpers import today_local

BASE = "/api/v1/dishes"

#: 本文件会**改动种子里的这道菜**（把配方整体替换掉）。
#: 会话级的收尾要等整个测试跑完才把种子灌回去，中间这段时间它一直是残缺的，
#: 后面的用例（例如校准要拿历史和配方对照）就会读到一个自相矛盾的库——
#: 历史总量是按原配方生成的，配方却已经变了。所以这道菜用完就地还原。
SEEDED_DISH = "清炒西兰花"


@pytest.fixture(autouse=True)
def restore_seeded_recipe() -> Iterator[None]:
    """把这道菜的配方在用例前后各快照、还原一次，避免污染后面的用例。"""

    def snapshot() -> tuple[int, list[dict], list[dict]] | None:
        with get_session_factory()() as session:
            dish = session.scalar(select(Dish).where(Dish.name == SEEDED_DISH))
            if dish is None:
                return None
            items = [
                {
                    "ingredient_id": row.ingredient_id,
                    "quantity_per_serving_g": row.quantity_per_serving_g,
                    "edible_ratio_override": row.edible_ratio_override,
                }
                for row in session.scalars(select(RecipeItem).where(RecipeItem.dish_id == dish.id))
            ]
            seasonings = [
                {
                    "seasoning_id": row.seasoning_id,
                    "quantity_per_serving_g": row.quantity_per_serving_g,
                }
                for row in session.scalars(
                    select(RecipeSeasoning).where(RecipeSeasoning.dish_id == dish.id)
                )
            ]
            return dish.recipe_version, items, seasonings

    def restore(state: tuple[int, list[dict], list[dict]] | None) -> None:
        if state is None:
            return
        version, items, seasonings = state
        with get_session_factory()() as session:
            dish = session.scalar(select(Dish).where(Dish.name == SEEDED_DISH))
            if dish is None:
                return
            session.execute(delete(RecipeItem).where(RecipeItem.dish_id == dish.id))
            session.execute(delete(RecipeSeasoning).where(RecipeSeasoning.dish_id == dish.id))
            for row in items:
                session.add(RecipeItem(dish_id=dish.id, **row))
            for row in seasonings:
                session.add(RecipeSeasoning(dish_id=dish.id, **row))
            dish.recipe_version = version
            session.commit()

    state = snapshot()
    yield
    restore(state)


def _id_of(client: TestClient, path: str, name: str) -> str:
    body = client.get(path, params={"keyword": name, "page_size": 100}).json()
    assert body["total"] >= 1, f"种子数据里应当有「{name}」"
    return body["items"][0]["id"]


def _rice_id(client: TestClient) -> str:
    return _id_of(client, "/api/v1/ingredients", "大米")


def _recipe_payload(client: TestClient, rice_g: str) -> dict:
    return {
        "ingredients": [{"ingredient_id": _rice_id(client), "quantity_per_serving_g": rice_g}],
        "seasonings": [],
    }


def _create_staple(client: TestClient, *, rice_g: str = "80.000") -> dict:
    created = client.post(
        BASE,
        json={
            "name": f"配方测试菜-{uuid4().hex[:8]}",
            "category": "STAPLE",
            "cooking_method": "STEAM",
            "standard_serving_g": "200.00",
            "servings_per_pot": "80.00",
            "allergens": [],
            "recipe": _recipe_payload(client, rice_g),
        },
    )
    assert created.status_code == 201, created.text
    return created.json()


def _energy(session: Session, dish_id: str) -> Decimal | None:
    session.expire_all()
    return session.scalar(
        select(DishNutrition.energy_kcal)
        .where(
            DishNutrition.dish_id == dish_id,
            DishNutrition.caliber == NutrientCaliber.PER_SERVING,
            DishNutrition.value_type == NutritionValueType.THEORETICAL,
        )
        .limit(1)
    )


def test_replacing_recipe_bumps_version_and_keeps_exactly_one_row(
    as_recorder: TestClient,
) -> None:
    dish = _create_staple(as_recorder)
    assert dish["recipe_version"] == 1

    response = as_recorder.put(
        f"{BASE}/{dish['id']}/recipe", json=_recipe_payload(as_recorder, "100.000")
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["recipe_version"] == 2
    # 整体替换：原来那一行必须消失，不能变成两行
    assert len(body["dish"]["recipe"]["ingredients"]) == 1
    assert body["dish"]["recipe"]["ingredients"][0]["quantity_per_serving_g"] == "100.000"


def test_saving_identical_recipe_does_not_bump_version(as_recorder: TestClient) -> None:
    """版本号要代表「配方确实变过几次」，重复保存同样的内容不该制造版本噪声。"""
    dish = _create_staple(as_recorder, rice_g="80.000")

    body = as_recorder.put(
        f"{BASE}/{dish['id']}/recipe", json=_recipe_payload(as_recorder, "80.000")
    ).json()

    assert body["recipe_version"] == 1
    assert body["recomputed_rows"] == 0


def test_recipe_snapshot_is_recorded_in_audit(as_recorder: TestClient, db_session: Session) -> None:
    dish = _create_staple(as_recorder, rice_g="80.000")

    as_recorder.put(f"{BASE}/{dish['id']}/recipe", json=_recipe_payload(as_recorder, "60.000"))

    entries = list(
        db_session.scalars(
            select(AuditLog)
            .where(AuditLog.entity_id == dish["id"], AuditLog.action == AuditAction.UPDATE)
            .order_by(AuditLog.created_at)
        )
    )
    assert entries, "配方改动必须留痕"
    latest = entries[-1]
    assert latest.before["ingredients"][0]["quantity_g"] == "80.000"
    assert latest.after["ingredients"][0]["quantity_g"] == "60.000"
    assert "v2" in (latest.note or "")


def test_recipe_change_does_not_rewrite_historical_nutrition(
    as_recorder: TestClient, db_session: Session
) -> None:
    """配方一改，过去日期的营养结果保持原样。

    历史看板、大屏回看与回测都依赖当时的配方口径；普通编辑只能影响今天和未来。
    """
    dish_id = _id_of(as_recorder, BASE, "清炒西兰花")
    past = db_session.scalar(
        select(DishNutrition)
        .where(
            DishNutrition.dish_id == dish_id,
            DishNutrition.date < today_local(),
            DishNutrition.caliber == NutrientCaliber.PER_SERVING,
            DishNutrition.value_type == NutritionValueType.THEORETICAL,
        )
        .order_by(DishNutrition.date.desc())
        .limit(1)
    )
    assert past is not None
    before = past.energy_kcal
    # 西兰花 110 克 ×0.83 食部、胡萝卜 15 克 ×0.96 食部、大豆油 5 克、食盐 1 克
    # → 32.95 + 5.64 + 44.17 + 0 = 82.76
    assert before == Decimal("82.76")

    broccoli = _id_of(as_recorder, "/api/v1/ingredients", "西兰花")
    carrot = _id_of(as_recorder, "/api/v1/ingredients", "胡萝卜")
    result = as_recorder.put(
        f"{BASE}/{dish_id}/recipe",
        json={
            "ingredients": [
                {"ingredient_id": broccoli, "quantity_per_serving_g": "110.000"},
                {"ingredient_id": carrot, "quantity_per_serving_g": "30.000"},
            ],
            "seasonings": [],
        },
    )

    assert result.status_code == 200, result.text

    db_session.expire_all()
    after = db_session.get(DishNutrition, past.id)
    assert after is not None
    assert after.energy_kcal == before


def test_historical_calibers_remain_both_present(
    as_recorder: TestClient, db_session: Session
) -> None:
    """普通配方编辑不删除历史行；单份与人均两种口径都还在。"""
    dish_id = _id_of(as_recorder, BASE, "清炒西兰花")
    as_recorder.put(
        f"{BASE}/{dish_id}/recipe",
        json={
            "ingredients": [
                {
                    "ingredient_id": _id_of(as_recorder, "/api/v1/ingredients", "西兰花"),
                    "quantity_per_serving_g": "110.000",
                }
            ],
            "seasonings": [],
        },
    )

    db_session.expire_all()
    calibers = set(
        db_session.scalars(select(DishNutrition.caliber).where(DishNutrition.dish_id == dish_id))
    )

    assert NutrientCaliber.PER_SERVING in calibers
    assert NutrientCaliber.PER_CAPITA in calibers

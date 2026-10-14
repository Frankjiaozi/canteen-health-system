"""配方维护：整体替换、版本递增、留痕，以及保存后自动重算营养。"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from app.modules.audit.models import AuditLog
from app.modules.nutrition.models import DishNutrition
from app.shared.enums import AuditAction, NutrientCaliber, NutritionValueType
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

BASE = "/api/v1/dishes"


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


def test_recipe_change_recomputes_nutrition_for_historical_dates(
    as_recorder: TestClient, db_session: Session
) -> None:
    """配方一改，这道菜**所有供应过的日子**的营养结果都要跟着变。

    只改最近一天是不够的：大屏看当天，看板、抽样对比与预测回测看的是历史，
    几处必须一起对齐，否则同一个数值在不同界面上对不上。
    """
    dish_id = _id_of(as_recorder, BASE, "清炒西兰花")
    before = _energy(db_session, dish_id)
    assert before == Decimal("83.43")

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
    assert result.json()["recomputed_rows"] > 0

    after = _energy(db_session, dish_id)
    # 这次改动去掉了 5 克大豆油，能量必然下降
    assert after is not None and after < before


def test_both_calibers_are_recomputed(as_recorder: TestClient, db_session: Session) -> None:
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

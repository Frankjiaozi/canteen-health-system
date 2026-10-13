"""食材库的写入接口：新增、修改、软删除。"""

from __future__ import annotations

from uuid import uuid4

from app.modules.ingredient.models import Ingredient
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from .conftest import BASE, new_ingredient_payload


def test_create_returns_the_created_ingredient(as_recorder: TestClient) -> None:
    payload = new_ingredient_payload()

    response = as_recorder.post(BASE, json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == payload["name"]
    assert body["category_label"] == "蔬菜类"
    assert body["is_active"] is True
    assert body["energy_kcal"] == "25.50"


def test_create_rejects_duplicate_name(as_recorder: TestClient) -> None:
    payload = new_ingredient_payload()
    assert as_recorder.post(BASE, json=payload).status_code == 201

    duplicate = as_recorder.post(BASE, json=payload)

    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "conflict"
    assert "已存在" in duplicate.json()["message"]


def test_create_rejects_impossible_edible_ratio(as_recorder: TestClient) -> None:
    payload = new_ingredient_payload()
    payload["edible_ratio"] = "1.5"

    response = as_recorder.post(BASE, json=payload)

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_create_rejects_missing_data_source(as_recorder: TestClient) -> None:
    """营养数据必须标注来源，缺了就拒绝写入。"""
    payload = new_ingredient_payload()
    payload.pop("data_source")

    assert as_recorder.post(BASE, json=payload).status_code == 422


def test_update_only_touches_submitted_fields(as_recorder: TestClient) -> None:
    created = as_recorder.post(BASE, json=new_ingredient_payload()).json()

    response = as_recorder.patch(f"{BASE}/{created['id']}", json={"sodium_mg": "99.90"})

    assert response.status_code == 200
    body = response.json()
    assert body["sodium_mg"] == "99.90"
    assert body["energy_kcal"] == created["energy_kcal"]
    assert body["data_source"] == created["data_source"]


def test_update_rejects_unknown_field(as_recorder: TestClient) -> None:
    created = as_recorder.post(BASE, json=new_ingredient_payload()).json()

    response = as_recorder.patch(f"{BASE}/{created['id']}", json={"is_active": False})

    assert response.status_code == 422


def test_update_rejects_name_taken_by_another(as_recorder: TestClient) -> None:
    first = as_recorder.post(BASE, json=new_ingredient_payload()).json()
    second = as_recorder.post(BASE, json=new_ingredient_payload()).json()

    response = as_recorder.patch(f"{BASE}/{second['id']}", json={"name": first["name"]})

    assert response.status_code == 409


def test_update_unknown_ingredient_returns_404(as_recorder: TestClient) -> None:
    response = as_recorder.patch(f"{BASE}/{uuid4()}", json={"note": "不存在"})

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_deactivate_is_a_soft_delete(as_recorder: TestClient, db_session: Session) -> None:
    created = as_recorder.post(BASE, json=new_ingredient_payload()).json()

    response = as_recorder.delete(f"{BASE}/{created['id']}")

    assert response.status_code == 200
    assert response.json()["is_active"] is False
    # 默认列表不再包含它
    assert as_recorder.get(BASE, params={"keyword": created["name"]}).json()["total"] == 0
    # 数据仍在：被配方引用过的食材一旦真的消失，历史营养结果就回溯不了
    with_inactive = as_recorder.get(
        BASE, params={"keyword": created["name"], "include_inactive": True}
    ).json()
    assert with_inactive["total"] == 1

    stored = db_session.get(Ingredient, created["id"])
    assert stored is not None and stored.is_active is False


def test_deactivate_is_idempotent(as_recorder: TestClient) -> None:
    created = as_recorder.post(BASE, json=new_ingredient_payload()).json()

    first = as_recorder.delete(f"{BASE}/{created['id']}")
    second = as_recorder.delete(f"{BASE}/{created['id']}")

    assert first.status_code == second.status_code == 200
    assert second.json()["is_active"] is False

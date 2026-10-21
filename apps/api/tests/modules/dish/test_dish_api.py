"""菜品接口：CRUD、权限、校验与留痕。"""

from __future__ import annotations

from uuid import UUID, uuid4

from app.modules.audit.models import AuditLog
from app.modules.dish.models import Dish
from app.shared.enums import AuditAction, CookingMethod, DishCategory
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

BASE = "/api/v1/dishes"


def _ingredient_id(client: TestClient, name: str) -> str:
    body = client.get("/api/v1/ingredients", params={"keyword": name}).json()
    assert body["total"] >= 1, f"种子数据里应当有食材「{name}」"
    return body["items"][0]["id"]


def _seasoning_id(client: TestClient, name: str) -> str:
    body = client.get("/api/v1/seasonings", params={"keyword": name}).json()
    assert body["total"] >= 1, f"种子数据里应当有调味料「{name}」"
    return body["items"][0]["id"]


def _payload(name: str | None = None) -> dict[str, object]:
    return {
        "name": name or f"测试菜品-{uuid4().hex[:8]}",
        "category": DishCategory.VEGETABLE.value,
        "cooking_method": CookingMethod.STIR_FRY.value,
        "standard_serving_g": "150.00",
        "servings_per_pot": "40.00",
        "allergens": [],
    }


def test_list_requires_login(client: TestClient) -> None:
    assert client.get(BASE).status_code == 401


def test_seeded_dishes_are_listed_with_nutrition(as_recorder: TestClient) -> None:
    body = as_recorder.get(BASE, params={"page_size": 100}).json()

    assert body["total"] >= 20, "验收要求不少于 20 道菜"
    names = {item["name"] for item in body["items"]}
    assert {"米饭", "番茄炒蛋", "红烧肉", "清蒸鲈鱼", "干煸豆角"} <= names

    rice = next(item for item in body["items"] if item["name"] == "米饭")
    assert rice["nutrition"] is not None
    # 米饭配方：大米 80 克、无调味料 → 0.8 × 352.06（稻米(均值) 条目的能量）
    assert rice["nutrition"]["energy_kcal"] == "281.65"
    assert rice["category_label"] == "主食"
    assert rice["cooking_method_label"] == "蒸"


def test_create_without_recipe_has_no_nutrition(as_recorder: TestClient) -> None:
    created = as_recorder.post(BASE, json=_payload())

    assert created.status_code == 201
    body = created.json()
    assert body["nutrition"] is None
    assert body["recipe_version"] == 1
    assert body["recipe"]["ingredients"] == []

    # 没有配方明细就没有可算的东西：列表里也应当是空，而不是一个像 0 的假值
    listed = as_recorder.get(BASE, params={"keyword": body["name"]}).json()["items"][0]
    assert listed["nutrition"] is None


def test_create_with_recipe_computes_nutrition(as_recorder: TestClient) -> None:
    name = f"测试菜品-{uuid4().hex[:8]}"
    payload = {
        **_payload(name),
        "recipe": {
            "ingredients": [
                {
                    "ingredient_id": _ingredient_id(as_recorder, "大米"),
                    "quantity_per_serving_g": "80.000",
                }
            ],
            "seasonings": [],
        },
    }

    body = as_recorder.post(BASE, json=payload).json()

    assert body["recipe"]["ingredients"][0]["ingredient_name"] == "大米"
    assert body["recipe_version"] == 1
    # 大米 80 克、无调味料 → 0.8 × 352.06；种子里的米饭是同一个配方，两个值必须一致
    rice = as_recorder.get(BASE, params={"keyword": "米饭"}).json()["items"][0]
    assert rice["nutrition"]["date"] is not None, "米饭在功能验证历史里供应过，读的是落库快照"
    assert body["nutrition"]["energy_kcal"] == rice["nutrition"]["energy_kcal"] == "281.65"
    # 现算的预览不属于任何一天，所以没有日期——它只用于列表摘要，不是可追溯的正式结果
    assert body["nutrition"]["date"] is None

    # 列表里同样要看得到：建库的人录完配方就要能核对数值，
    # 而不是等到这道菜第一次被排进菜单
    listed = as_recorder.get(BASE, params={"keyword": name}).json()
    assert listed["total"] == 1
    assert listed["items"][0]["nutrition"]["energy_kcal"] == "281.65"
    assert listed["items"][0]["nutrition"]["date"] is None


def test_recipe_requires_at_least_one_ingredient(as_recorder: TestClient) -> None:
    payload = {**_payload(), "recipe": {"ingredients": [], "seasonings": []}}

    response = as_recorder.post(BASE, json=payload)

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_recipe_rejects_duplicate_ingredient(as_recorder: TestClient) -> None:
    rice = _ingredient_id(as_recorder, "大米")
    payload = {
        **_payload(),
        "recipe": {
            "ingredients": [
                {"ingredient_id": rice, "quantity_per_serving_g": "50.000"},
                {"ingredient_id": rice, "quantity_per_serving_g": "30.000"},
            ],
            "seasonings": [],
        },
    }

    assert as_recorder.post(BASE, json=payload).status_code == 422


def test_recipe_rejects_unknown_ingredient(as_recorder: TestClient) -> None:
    payload = {
        **_payload(),
        "recipe": {
            "ingredients": [{"ingredient_id": str(uuid4()), "quantity_per_serving_g": "50.000"}],
            "seasonings": [],
        },
    }

    response = as_recorder.post(BASE, json=payload)

    assert response.status_code == 422
    assert response.json()["code"] == "business_rule_violated"
    assert "食材库" in response.json()["message"]


def test_update_and_deactivate(as_recorder: TestClient, db_session: Session) -> None:
    created = as_recorder.post(BASE, json=_payload()).json()

    updated = as_recorder.patch(f"{BASE}/{created['id']}", json={"standard_serving_g": "180.00"})
    assert updated.status_code == 200
    assert updated.json()["standard_serving_g"] == "180.00"

    removed = as_recorder.delete(f"{BASE}/{created['id']}")
    assert removed.status_code == 200
    assert removed.json()["is_active"] is False

    stored = db_session.get(Dish, created["id"])
    assert stored is not None and stored.is_active is False


def test_duplicate_name_is_rejected(as_recorder: TestClient) -> None:
    payload = _payload()
    assert as_recorder.post(BASE, json=payload).status_code == 201
    assert as_recorder.post(BASE, json=payload).status_code == 409


def test_school_admin_is_read_only(as_school_admin: TestClient) -> None:
    assert as_school_admin.get(BASE).status_code == 200
    assert as_school_admin.post(BASE, json=_payload()).status_code == 403


def test_create_is_audited(as_recorder: TestClient, db_session: Session) -> None:
    created = as_recorder.post(BASE, json=_payload()).json()

    entry = db_session.scalar(
        select(AuditLog).where(AuditLog.entity_type == "dish", AuditLog.entity_id == created["id"])
    )

    assert entry is not None
    assert entry.action == AuditAction.CREATE
    assert entry.actor_name == "王芳（录入员）"


def test_get_detail_returns_full_recipe(as_recorder: TestClient) -> None:
    listing = as_recorder.get(BASE, params={"keyword": "番茄炒蛋"}).json()
    dish_id = listing["items"][0]["id"]

    detail = as_recorder.get(f"{BASE}/{dish_id}").json()

    ingredient_names = {line["ingredient_name"] for line in detail["recipe"]["ingredients"]}
    assert {"番茄", "鸡蛋"} <= ingredient_names
    seasoning_names = {line["seasoning_name"] for line in detail["recipe"]["seasonings"]}
    assert {"大豆油", "食盐", "白砂糖"} <= seasoning_names
    assert all(UUID(line["ingredient_id"]) for line in detail["recipe"]["ingredients"])

"""食材库的读取接口：分页、过滤、参数校验。"""

from __future__ import annotations

from app.shared.enums import IngredientCategory
from fastapi.testclient import TestClient

from .conftest import BASE

#: 种子脚本内置的 22 种演示食材。断言用「这些必须都在」而不是「总数恰好 22」，
#: 因为写入用例会在同一个开发库里留下自己的测试数据。
SEEDED_NAMES = {
    "大米",
    "小麦粉",
    "马铃薯",
    "大白菜",
    "西兰花",
    "番茄",
    "黄瓜",
    "胡萝卜",
    "青椒",
    "洋葱",
    "油菜",
    "木耳（干）",
    "紫菜（干）",
    "鸡蛋",
    "猪肉（瘦）",
    "鸡胸肉",
    "牛肉（瘦）",
    "对虾",
    "豆腐（北）",
    "苹果",
    "牛奶",
    "芝麻油",
}


def test_list_requires_login(client: TestClient) -> None:
    assert client.get(BASE).status_code == 401


def test_list_returns_seeded_ingredients(as_recorder: TestClient) -> None:
    response = as_recorder.get(BASE, params={"page_size": 100, "include_inactive": True})

    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 1
    assert body["page_size"] == 100
    assert body["total"] >= len(SEEDED_NAMES)
    assert {item["name"] for item in body["items"]} >= SEEDED_NAMES
    # 中文类别随响应下发，前端不用自己维护一份文案映射
    labels = {item["category_label"] for item in body["items"]}
    assert {"蔬菜类", "蛋类", "畜禽肉类"} <= labels


def test_list_paginates_without_overlap(as_recorder: TestClient) -> None:
    first = as_recorder.get(BASE, params={"page": 1, "page_size": 5}).json()
    second = as_recorder.get(BASE, params={"page": 2, "page_size": 5}).json()

    assert len(first["items"]) == 5
    assert len(second["items"]) == 5
    assert first["total"] == second["total"]
    assert {item["id"] for item in first["items"]}.isdisjoint(
        {item["id"] for item in second["items"]}
    )


def test_list_filters_by_keyword(as_recorder: TestClient) -> None:
    body = as_recorder.get(BASE, params={"keyword": "西兰花"}).json()

    assert body["total"] == 1
    assert body["items"][0]["name"] == "西兰花"


def test_list_filters_by_category(as_recorder: TestClient) -> None:
    body = as_recorder.get(BASE, params={"category": IngredientCategory.EGG.value}).json()

    assert body["total"] >= 1
    assert all(item["category"] == IngredientCategory.EGG.value for item in body["items"])


def test_list_rejects_unknown_category(as_recorder: TestClient) -> None:
    response = as_recorder.get(BASE, params={"category": "NOT_A_CATEGORY"})

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_pagination_bounds_are_validated(as_recorder: TestClient) -> None:
    assert as_recorder.get(BASE, params={"page": 0}).status_code == 422
    assert as_recorder.get(BASE, params={"page_size": 1000}).status_code == 422


def test_get_single_ingredient(as_recorder: TestClient) -> None:
    listed = as_recorder.get(BASE, params={"keyword": "西兰花"}).json()["items"][0]

    response = as_recorder.get(f"{BASE}/{listed['id']}")

    assert response.status_code == 200
    assert response.json()["name"] == "西兰花"
    assert response.json()["data_source"]

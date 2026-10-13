"""食材库测试的共用夹具。"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from app.db.seed import DEFAULT_DEMO_PASSWORD
from app.shared.enums import IngredientCategory
from fastapi.testclient import TestClient

BASE = "/api/v1/ingredients"


def login(client: TestClient, username: str) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": DEFAULT_DEMO_PASSWORD},
    )
    assert response.status_code == 200, response.text


@pytest.fixture
def as_recorder(client: TestClient) -> Iterator[TestClient]:
    login(client, "recorder")
    yield client
    client.cookies.clear()


@pytest.fixture
def as_school_admin(client: TestClient) -> Iterator[TestClient]:
    login(client, "school")
    yield client
    client.cookies.clear()


def new_ingredient_payload(name: str | None = None) -> dict[str, object]:
    return {
        "name": name or f"测试食材-{uuid4().hex[:8]}",
        "category": IngredientCategory.VEGETABLE.value,
        "energy_kcal": "25.5",
        "protein_g": "1.800",
        "fat_g": "0.300",
        "carb_g": "4.100",
        "sodium_mg": "12.30",
        "edible_ratio": "0.9200",
        "unit_price": "4.50",
        "data_source": "接口测试构造",
        "source_version": "test",
    }

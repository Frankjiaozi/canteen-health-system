"""食材库测试的共用数据构造。

登录相关的夹具（as_recorder / as_school_admin 等）统一放在 tests/conftest.py，
各业务域测试共用。
"""

from __future__ import annotations

from uuid import uuid4

from app.shared.enums import IngredientCategory

BASE = "/api/v1/ingredients"


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

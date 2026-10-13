"""数据层集成测试：验证类型在真实 PostgreSQL 上的往返行为。

前置：本地数据库已启动（`pnpm db:up`）且已执行 `pnpm db:migrate`。
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from app.modules.ingredient.models import Ingredient
from app.shared.enums import IngredientCategory
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def _unique_name(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8]}"


def test_uuid_enum_and_numeric_roundtrip(db_session: Session) -> None:
    ingredient = Ingredient(
        name=_unique_name("测试食材"),
        category=IngredientCategory.VEGETABLE,
        energy_kcal=Decimal("34.00"),
        protein_g=Decimal("4.100"),
        fat_g=Decimal("0.600"),
        carb_g=Decimal("4.300"),
        sodium_mg=Decimal("18.80"),
        edible_ratio=Decimal("0.9000"),
        data_source="单元测试构造，非真实数据",
    )
    db_session.add(ingredient)
    db_session.flush()

    assert ingredient.id is not None, "UUID 主键应由应用层生成"

    db_session.expire_all()
    stored = db_session.get(Ingredient, ingredient.id)
    assert stored is not None
    # 枚举读回的是枚举成员而不是裸字符串
    assert stored.category is IngredientCategory.VEGETABLE
    # 数值精度按列定义保留
    assert stored.energy_kcal == Decimal("34.00")
    assert stored.protein_g == Decimal("4.100")
    assert stored.edible_ratio == Decimal("0.9000")
    # server_default 生效
    assert stored.is_active is True
    assert stored.created_at is not None
    assert stored.created_at.tzinfo is not None


def test_missing_nutrients_are_stored_as_null_not_zero(db_session: Session) -> None:
    """食物成分表缺项必须保持 NULL：写成 0 会让营养核算静默失真。"""
    ingredient = Ingredient(
        name=_unique_name("测试食材-缺项"),
        category=IngredientCategory.OTHER,
        data_source="单元测试构造，非真实数据",
    )
    db_session.add(ingredient)
    db_session.flush()

    db_session.expire_all()
    stored = db_session.get(Ingredient, ingredient.id)
    assert stored is not None
    assert stored.energy_kcal is None
    assert stored.sodium_mg is None


def test_enum_check_constraint_rejects_unknown_value(db_session: Session) -> None:
    """数据库层必须挡住在代码里绕过枚举写进来的非法取值。"""
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO ingredients (id, name, category, edible_ratio, data_source,"
                " created_at, updated_at) VALUES"
                " (gen_random_uuid(), :name, 'NOT_A_CATEGORY', 1.0, 'test', now(), now())"
            ),
            {"name": _unique_name("非法类别")},
        )

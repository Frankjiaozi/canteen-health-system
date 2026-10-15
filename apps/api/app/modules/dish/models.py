"""菜品与标准配方模型。

配方是全系统最需要人工投入、也最不能被推翻的数据：营养计算的一切推导都以它为准。

用量单位统一为**克**（列名带 `_g` 后缀即为此意）：需求里的「计量单位」在本系统
收敛为固定口径，避免出现 ml / 勺 这类无法参与计算的单位。
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.mixins import SoftDeleteMixin
from app.db.types import enum_check, enum_type
from app.shared.enums import CookingMethod, DishCategory


class Dish(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """菜品。菜单轮换的基本单位。"""

    __tablename__ = "dishes"

    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    category: Mapped[DishCategory] = mapped_column(enum_type(DishCategory), nullable=False)
    cooking_method: Mapped[CookingMethod] = mapped_column(
        enum_type(CookingMethod), nullable=False, index=True
    )

    # 标准份量：一份菜的可食部重量（克）
    standard_serving_g: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    # 单锅制作份数，用于把锅次换算成份数
    servings_per_pot: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)

    # 过敏原标记，例如 ["蛋", "花生"]
    allergens: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    # 配方版本：每次修改配方递增，使历史营养结果能对应到当时用的配方
    recipe_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))

    #: 早餐固定供应。
    #:
    #: 早餐不走推荐求解：学校早餐是每天固定那几样，把它当成「待优化的选择」既不符合
    #: 现实，也会和午晚餐用同一套目标算出同一份菜单。勾了这个标记的菜构成每天的早餐，
    #: 同时**不再进入午晚餐的候选池**——否则同一个菜会在一天里出现两次。
    is_breakfast_staple: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    note: Mapped[str | None] = mapped_column(String(255))

    __table_args__ = (
        enum_check("category", DishCategory),
        enum_check("cooking_method", CookingMethod),
    )

    def __repr__(self) -> str:
        return f"<Dish {self.name}>"


class RecipeItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """配方中的一条食材用量。"""

    __tablename__ = "recipe_items"

    dish_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dishes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingredients.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # 单份用量（克，市品重量，计算时按可食部比例折算）
    quantity_per_serving_g: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False)
    # 需要覆盖食材库默认可食部比例时填写
    edible_ratio_override: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    note: Mapped[str | None] = mapped_column(String(255))

    __table_args__ = (UniqueConstraint("dish_id", "ingredient_id"),)


class RecipeSeasoning(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """配方中分摊到单份的调味料用量。

    与 `RecipeItem` 分开建表，是因为调味料在营养计算里承担的是「校准锚点」角色，
    而不是普通食材：当日实际用油用盐量就是拿它与配方推算总量做比对的。
    """

    __tablename__ = "recipe_seasonings"

    dish_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dishes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    seasoning_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("seasonings.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    quantity_per_serving_g: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False)
    note: Mapped[str | None] = mapped_column(String(255))

    __table_args__ = (UniqueConstraint("dish_id", "seasoning_id"),)

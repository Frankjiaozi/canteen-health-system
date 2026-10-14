"""食材模型。

营养成分一律以**每 100 克可食部**计，这是《中国食物成分表》的口径，
也是全系统营养计算的唯一基准。
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.mixins import SoftDeleteMixin
from app.db.types import enum_check, enum_type
from app.shared.enums import IngredientCategory


class Ingredient(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """食材。

    五项营养指标刻意设为**可空**：食物成分表里部分条目确实缺项，
    把缺失写成 0 会让营养核算静默失真。计算引擎遇到空值时会记录到
    计算结果的可追溯快照里，并据此放宽误差区间。
    """

    __tablename__ = "ingredients"

    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    category: Mapped[IngredientCategory] = mapped_column(
        enum_type(IngredientCategory), nullable=False, index=True
    )

    # 每 100 克可食部
    energy_kcal: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    protein_g: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    fat_g: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    carb_g: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    sodium_mg: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))

    # 可食部比例（0~1），用于把市品重量折算成可食部重量
    edible_ratio: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False, server_default=text("1.0")
    )
    #: 单价按**市品重量**计（元 / 公斤），不是可食部单价。
    #: 买菜按市品付钱、做菜按可食部算营养，两者口径不同不能混：
    #: 用可食部重量乘市品单价会把成本算低（西兰花低 17%、鲈鱼低 42%）。
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))

    # 数据来源必须逐条可追溯
    data_source: Mapped[str] = mapped_column(String(128), nullable=False)
    source_version: Mapped[str | None] = mapped_column(String(64))
    note: Mapped[str | None] = mapped_column(String(255))

    __table_args__ = (enum_check("category", IngredientCategory),)

    def __repr__(self) -> str:
        return f"<Ingredient {self.name}>"

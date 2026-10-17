"""调味料模型。

调味料单独建表而不是混进食材库，原因有两条：它们既是营养计算的关键变量
（油盐糖的量直接决定钠与脂肪），又是每日采集的对象（M2 每天只需要填这几个数字）。
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.mixins import SoftDeleteMixin
from app.db.types import enum_check, enum_type
from app.shared.enums import SeasoningCategory


class Seasoning(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """调味料，营养成分以每 100 克计（与食材库同一口径，便于统一计算）。"""

    __tablename__ = "seasonings"

    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    category: Mapped[SeasoningCategory] = mapped_column(
        enum_type(SeasoningCategory), nullable=False, index=True
    )
    unit: Mapped[str] = mapped_column(String(16), nullable=False, server_default="g")

    # 每 100 克
    energy_kcal: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    protein_g: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    fat_g: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    carb_g: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    sodium_mg: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))

    #: 单价按**市品重量**计（元 / 公斤）——与食材同一个口径，便于成本相加
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    data_source: Mapped[str | None] = mapped_column(String(128))
    #: 平台条目名 + 条目 ID —— 与食材库同一条要求：数值要能回溯到具体来源
    source_version: Mapped[str | None] = mapped_column(String(64))
    note: Mapped[str | None] = mapped_column(String(255))

    __table_args__ = (enum_check("category", SeasoningCategory),)

    def __repr__(self) -> str:
        return f"<Seasoning {self.name}>"

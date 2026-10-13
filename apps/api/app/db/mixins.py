"""跨业务域复用的列 Mixin。"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Boolean, Numeric, text
from sqlalchemy.orm import Mapped, mapped_column


class NutrientColumnsMixin:
    """五项核心营养指标，全部不可空。用于「计算结果」表。

    注意：食材库不继承本 Mixin——食物成分表里部分营养素确实缺失，
    那些列必须是可空的，把「未知」写成 0 会造成静默失真。
    """

    energy_kcal: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    protein_g: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    fat_g: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    carb_g: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    sodium_mg: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)


class SoftDeleteMixin:
    """软删除标记。

    被配方、菜单或每日记录引用过的数据一律不做物理删除，只置 `is_active=False`；
    这样历史营养结果与审计记录始终可回溯。
    """

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

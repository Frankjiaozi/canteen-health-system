"""膳食指南基准的对照逻辑（纯函数）。

公开大屏与管理端看板都要做「实际值 vs 基准」的判断，规则必须只有一份，
否则同一份数据在两个界面上会得出不同结论。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

#: 对照状态：达标 / 超上限 / 低于推荐 / 无数据
STATUS_OK = "ok"
STATUS_OVER = "over"
STATUS_UNDER = "under"
STATUS_UNKNOWN = "unknown"


class DinerCounted(Protocol):
    """只要求提供人次与某个用量字段，便于测试时用简单对象替代 ORM 行。"""

    diner_count: int


def sum_per_capita_across_meals(logs: Iterable[DinerCounted], field: str) -> Decimal | None:
    """当日人均累计：把每一餐的「总量 ÷ 该餐人次」相加。

    各餐次人次不同，因此不能先把总量加总再除一次——那会算成另一件事。
    例：午餐 500 人吃 1000 克、晚餐 100 人吃 400 克，人均日摄入是 2.0 + 4.0 = 6.0 克，
    而不是 1400 ÷ 600 ≈ 2.33 克。
    """
    usable = [log for log in logs if log.diner_count > 0]
    if not usable:
        return None
    values = [getattr(log, field) for log in usable]
    # 一餐缺测就不能把其余餐次相加冒充“全天人均”：未知 + 已知仍然是未知。
    if any(value is None for value in values):
        return None
    total = sum(
        (value / Decimal(log.diner_count) for log, value in zip(usable, values, strict=True)),
        Decimal("0"),
    )
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def compare_to_standard(
    *,
    target_min: Decimal | None,
    target_max: Decimal | None,
    actual: Decimal | None,
) -> str:
    """与基准比较。

    「低于推荐」与「超出上限」是两件不同的事：烹调油不足是供给问题，
    食盐超标才是要警惕的方向，因此分开表达而不是笼统地叫「不达标」。
    """
    if actual is None:
        return STATUS_UNKNOWN
    if target_max is not None and actual > target_max:
        return STATUS_OVER
    if target_min is not None and actual < target_min:
        return STATUS_UNDER
    return STATUS_OK


def quantize(value: Decimal, digits: int) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)


def mean(values: Sequence[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))

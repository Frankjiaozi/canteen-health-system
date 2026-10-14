"""Decimal 的取整与快照处理。

接口一律以字符串回传 Decimal，并且**按列定义的小数位取整**。不这么做的话，
新建时回显的是请求值（25.5），查询时是数据库读回的值（25.50），同一个数在两种
路径下写法不同，前端对不齐、测试也会莫名其妙地飘。
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.shared.nutrients import NUTRIENT_SCALES

#: 营养列 + 营养类数据共用的通用列（食材、调味料、菜品都用这套）
COMMON_FIELD_SCALES: dict[str, int] = {
    **NUTRIENT_SCALES,
    "edible_ratio": 4,
    "unit_price": 2,
}


def quantize_to(value: Decimal | None, digits: int) -> Decimal | None:
    """按指定小数位取整；None 原样返回。"""
    if value is None:
        return None
    return value.quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)


def scale_field(value: Decimal | None, field: str) -> Decimal | None:
    """按字段名查表取整。字段不在表里时按两位处理。"""
    return quantize_to(value, COMMON_FIELD_SCALES.get(field, 2))


def snapshot(value: Decimal | None) -> str | None:
    """转成留痕用的字符串。"""
    return None if value is None else str(value)

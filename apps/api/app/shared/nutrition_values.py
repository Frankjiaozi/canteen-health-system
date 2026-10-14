"""同一道菜同一天可能同时存在三份营养结果，展示时该挑哪一份。

三层校准的产出是**并存**的：理论值、当日校准值、抽样实测值各占一行，谁也不覆盖谁。
好处是能并排对比与回溯，代价是每个读取方都必须明确回答「我要的是哪一份」。
把这件事收在这一处，是为了避免大屏和看板各自拍一个顺序——那种分歧不会报错，
只会让两个界面对同一道菜给出不同的数字，事后极难发现。

取舍顺序：**抽样实测 > 当日校准 > 配方理论**。依据是证据强度——称过的是事实，
闭环系数是从当日总用量反推的，配方理论值是基准。越靠前的证据越直接，就该越优先。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import case

from app.shared.enums import NutritionValueType

#: 数值越小越优先
VALUE_TYPE_PRIORITY: dict[NutritionValueType, int] = {
    NutritionValueType.SAMPLED: 0,
    NutritionValueType.CALIBRATED: 1,
    NutritionValueType.THEORETICAL: 2,
}

#: 参与取舍的全部数值类型
VALUE_TYPES: tuple[NutritionValueType, ...] = tuple(VALUE_TYPE_PRIORITY)

#: 给界面用的一句话说明：这个数是从哪一层来的
VALUE_TYPE_DESCRIPTIONS: dict[NutritionValueType, str] = {
    NutritionValueType.SAMPLED: "抽样称重实测",
    NutritionValueType.CALIBRATED: "按当日油盐糖实际用量校准",
    NutritionValueType.THEORETICAL: "按标准配方推算",
}


def priority_expression(column: Any) -> Any:
    """给 SQL 用的排序表达式：抽样在前、理论在最后。"""
    return case(VALUE_TYPE_PRIORITY, value=column, else_=len(VALUE_TYPE_PRIORITY))


def pick_best[RowT](rows: Iterable[RowT], *, dish_of: Any, value_type_of: Any) -> dict[Any, RowT]:
    """按菜品挑出优先级最高的那一行。

    在 Python 侧做取舍，是为了不依赖 PostgreSQL 特有的 DISTINCT ON；
    这里的数据量是「当天几道菜 × 最多三份」，一次查询取回再挑完全够用。
    """
    best: dict[Any, RowT] = {}
    for row in rows:
        key = dish_of(row)
        current = best.get(key)
        if (
            current is None
            or VALUE_TYPE_PRIORITY[value_type_of(row)] < VALUE_TYPE_PRIORITY[value_type_of(current)]
        ):
            best[key] = row
    return best

"""营养域的响应模型。

`StandardComparison` 放在营养域，因为膳食指南基准表归它所有；
公开大屏与管理端看板都复用它，保证同一个判断不会有两套实现。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class StandardComparison(BaseModel):
    """实际值与膳食指南量化基准的对照。"""

    code: str
    label: str
    unit: str
    target_min: str | None = None
    target_max: str | None = None
    actual: str | None = Field(default=None, description="实际值；人均口径或种类数")
    status: str = Field(description="ok / over / under / unknown")
    source: str
    source_quote: str | None = None


def to_comparison(
    *,
    code: str,
    label: str,
    unit: str,
    target_min: str | None,
    target_max: str | None,
    actual: str | None,
    status: str,
    source: str,
    source_quote: str | None,
) -> StandardComparison:
    return StandardComparison(
        code=code,
        label=label,
        unit=unit,
        target_min=target_min,
        target_max=target_max,
        actual=actual,
        status=status,
        source=source,
        source_quote=source_quote,
    )

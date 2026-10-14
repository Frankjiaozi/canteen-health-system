"""批量导入的响应模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

IssueSeverity = Literal["error", "warning"]


class ImportIssue(BaseModel):
    """一条逐行问题。error 会阻止导入，warning 只提示。"""

    severity: IssueSeverity
    sheet: str = Field(description="出问题的 sheet 名")
    row: int | None = Field(default=None, description="Excel 行号（含表头，从 1 开始）")
    field: str | None = Field(default=None, description="出问题的列")
    message: str


class ImportCounts(BaseModel):
    sheet: str
    created: int = 0
    updated: int = 0
    skipped: int = 0


class ImportReport(BaseModel):
    dry_run: bool = Field(description="true 表示只校验、未写库")
    ok: bool = Field(description="没有 error 才算通过；dry_run 下同样如此")
    counts: list[ImportCounts]
    issues: list[ImportIssue]
    recomputed_rows: int = Field(default=0, description="导入后重算的营养结果条数")

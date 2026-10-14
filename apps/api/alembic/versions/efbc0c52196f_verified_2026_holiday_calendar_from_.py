"""verified 2026 holiday calendar from official notice

Revision ID: efbc0c52196f
Revises: 851aae2a8e9b
Create Date: 2026-10-14 22:03:06.458115+08:00
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta

import sqlalchemy as sa
from alembic import op


revision: str = 'efbc0c52196f'
down_revision: str | None = '851aae2a8e9b'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: 放假区间（起, 止），含首尾
_HOLIDAY_WINDOWS: list[tuple[str, date, date]] = [
    ("元旦", date(2026, 1, 1), date(2026, 1, 3)),
    ("春节", date(2026, 2, 15), date(2026, 2, 23)),
    ("清明节", date(2026, 4, 4), date(2026, 4, 6)),
    ("劳动节", date(2026, 5, 1), date(2026, 5, 5)),
    ("端午节", date(2026, 6, 19), date(2026, 6, 21)),
    ("中秋节", date(2026, 9, 25), date(2026, 9, 27)),
    ("国庆节", date(2026, 10, 1), date(2026, 10, 7)),
]

#: 调休上班的周末
_WORKDAYS: list[tuple[str, date]] = [
    ("元旦", date(2026, 1, 4)),
    ("春节", date(2026, 2, 14)),
    ("春节", date(2026, 2, 28)),
    ("劳动节", date(2026, 5, 9)),
    ("国庆节", date(2026, 9, 20)),
    ("国庆节", date(2026, 10, 10)),
]

_SOURCE = "国务院办公厅《关于2026年部分节假日安排的通知》（国办发明电〔2025〕7号）"


def _upsert(day: date, name: str, kind: str, note: str) -> None:
    """按日期覆盖写入。

    用 ON CONFLICT DO UPDATE 而不是 DO NOTHING：这一条迁移的作用就是**取代**先前
    内置的那份「只标了节日当天、全部待核对」的日历，把它补成完整且已核对的。
    """
    op.execute(
        sa.text(
            """
            INSERT INTO holidays (id, date, name, kind, is_verified, source_note,
                                  created_at, updated_at)
            VALUES (gen_random_uuid(), :day, :name, :kind, true, :note, now(), now())
            ON CONFLICT (date) DO UPDATE
               SET name = EXCLUDED.name,
                   kind = EXCLUDED.kind,
                   is_verified = EXCLUDED.is_verified,
                   source_note = EXCLUDED.source_note,
                   updated_at = now()
            """
        ).bindparams(day=day, name=name, kind=kind, note=note)
    )


def upgrade() -> None:
    # 2026 年放假调休安排，逐条取自国务院办公厅通知原文。
    # 之前内置的那份只放了节日当天且全部标「待核对」；这里把它补成完整、已核对的日历，
    # 并补上六个调休上班的周末——少了它们，预测会在每周调休时把份数算低一大截。
    for name, start, end in _HOLIDAY_WINDOWS:
        day = start
        while day <= end:
            _upsert(day, f"{name}放假", "HOLIDAY", _SOURCE)
            day += timedelta(days=1)
    for name, day in _WORKDAYS:
        _upsert(day, f"{name}调休上班", "WORKDAY", _SOURCE)


def downgrade() -> None:
    """回到迁移前的样子：只保留节日当天，且全部标为待核对。"""
    op.execute(
        "DELETE FROM holidays WHERE date IN ("
        + ", ".join(f"DATE '{day.isoformat()}'" for _, day in _WORKDAYS)
        + ")"
    )
    op.execute(
        "UPDATE holidays SET is_verified = false,"
        " source_note = '待核对：放假区间与调休上班日须以国务院办公厅"
        "《关于2026年部分节假日安排的通知》为准'"
    )

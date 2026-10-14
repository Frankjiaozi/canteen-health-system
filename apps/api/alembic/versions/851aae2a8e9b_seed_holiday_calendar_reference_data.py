"""seed holiday calendar reference data

Revision ID: 851aae2a8e9b
Revises: 73492d83eb7d
Create Date: 2026-10-14 21:47:43.096884+08:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '851aae2a8e9b'
down_revision: str | None = '73492d83eb7d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 节假日日历是**参考数据**，不是演示数据：任何环境跑完迁移都该有它，
    # 否则预测会静默地不做节假日修正。放在演示种子脚本里会漏掉正式部署。
    #
    # 这里只放七个法定节日的公历日期（农历节日的公历日期由历法决定，可以确定）。
    # 放假区间与调休上班日由国务院办公厅通知决定，**没有可靠来源，因此不编造**——
    # 全部 is_verified=false，界面上有核对入口，核对后按通知补全。
    op.execute(
        sa.text(
            """
            INSERT INTO holidays (id, date, name, kind, is_verified, source_note,
                                  created_at, updated_at)
            VALUES
              (gen_random_uuid(), DATE '2026-01-01', '元旦',   'HOLIDAY', false, :note, now(), now()),
              (gen_random_uuid(), DATE '2026-02-17', '春节',   'HOLIDAY', false, :note, now(), now()),
              (gen_random_uuid(), DATE '2026-04-05', '清明节', 'HOLIDAY', false, :note, now(), now()),
              (gen_random_uuid(), DATE '2026-05-01', '劳动节', 'HOLIDAY', false, :note, now(), now()),
              (gen_random_uuid(), DATE '2026-06-19', '端午节', 'HOLIDAY', false, :note, now(), now()),
              (gen_random_uuid(), DATE '2026-09-25', '中秋节', 'HOLIDAY', false, :note, now(), now()),
              (gen_random_uuid(), DATE '2026-10-01', '国庆节', 'HOLIDAY', false, :note, now(), now())
            ON CONFLICT (date) DO NOTHING
            """
        ).bindparams(
            note="待核对：放假区间与调休上班日须以国务院办公厅《关于2026年部分节假日安排的通知》为准"
        )
    )


def downgrade() -> None:
    # 只回滚这份迁移插入的那七个日期，不动后来人工核对或补充的条目
    op.execute(
        "DELETE FROM holidays WHERE date IN ("
        "DATE '2026-01-01', DATE '2026-02-17', DATE '2026-04-05', DATE '2026-05-01',"
        " DATE '2026-06-19', DATE '2026-09-25', DATE '2026-10-01')"
    )

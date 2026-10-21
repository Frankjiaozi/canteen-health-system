"""命令行入口：按第一层计算并写入营养结果。

用法：

    pnpm db:compute              # 最近 14 天
    python -m app.modules.nutrition.compute --days 30
"""

from __future__ import annotations

import argparse

from app.core.logging import configure_logging, get_logger
from app.db.session import get_session_factory
from app.modules.nutrition import service

logger = get_logger("app.nutrition.compute")

#: 默认计算最近 8 周，与初始化种子的历史跨度对齐（见 app/db/seed.py 的 HISTORY_DAYS）。
#: 生产环境的定期重算可以用 --days 覆盖。
DEFAULT_DAYS = 56


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="按三层校准第一层计算营养结果")
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS,
        help=f"计算最近多少天（含今天），默认 {DEFAULT_DAYS} 天",
    )
    args = parser.parse_args(argv)

    configure_logging("INFO")
    logger.info("开始营养计算：统计最近 %d 天", args.days)

    with get_session_factory()() as session:
        report = service.compute_recent_days(session, days=args.days)

    logger.info("营养计算完成：%s", report.describe())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

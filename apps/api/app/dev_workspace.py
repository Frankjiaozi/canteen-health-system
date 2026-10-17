"""本机独立演示/测试库入口。固定库名，不接受任意目标，也不删除数据库。"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.core.config import Settings, get_settings

API_DIR = Path(__file__).resolve().parents[1]


def prepare(mode: str, *, refresh_seed: bool = False) -> None:
    initial = Settings()
    base = make_url(initial.database_url)
    if initial.is_production or base.host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("独立工作区仅支持本机开发数据库，拒绝操作 production 或远程数据库")
    target = "canteen_agent_demo" if mode == "demo" else "canteen_upgrade_test"
    admin_url = base.set(drivername="postgresql", database="postgres")
    try:
        with psycopg.connect(
            admin_url.render_as_string(hide_password=False), autocommit=True, connect_timeout=3
        ) as connection:
            found = connection.execute(
                "SELECT 1 FROM pg_database WHERE datname=%s", (target,)
            ).fetchone()
            if not found:
                connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target)))
    except psycopg.Error:
        raise SystemExit(
            "无法准备本机独立数据库，请先从系统菜单打开 Docker，并启动开发 PostgreSQL"
        ) from None
    os.environ["DATABASE_URL"] = base.set(database=target).render_as_string(hide_password=False)
    os.environ["APP_ENV"] = "test" if mode == "test" else "development"
    if mode in {"test", "demo"}:
        os.environ["ALLOW_OPEN_REGISTRATION"] = "true"
    get_settings.cache_clear()
    command.upgrade(Config(str(API_DIR / "alembic.ini")), "head")
    if mode == "demo":
        from app.db import seed
        from app.db.session import get_session_factory
        from app.modules.nutrition.service import compute_recent_days

        with get_session_factory()() as session:
            count = session.scalar(text("SELECT count(*) FROM dishes"))
            if not count or refresh_seed:
                seed.run(session)
                compute_recent_days(session, days=seed.HISTORY_DAYS)
                session.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["demo", "test"])
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--pytest", action="store_true")
    parser.add_argument("--refresh-seed", action="store_true")
    parser.add_argument("--port", type=int, default=8002)
    args, remaining = parser.parse_known_args()
    if args.serve and args.mode != "demo":
        parser.error("测试库不作为开发服务启动")
    if args.refresh_seed and args.mode != "demo":
        parser.error("刷新示例数据仅作用于独立演示库")
    prepare(args.mode, refresh_seed=args.refresh_seed)
    if args.pytest:
        if args.mode != "test":
            parser.error("测试只能在独立测试库运行")
        import pytest

        return pytest.main([argument for argument in remaining if argument != "--"])
    if args.serve:
        import uvicorn

        uvicorn.run(
            "app.main:app",
            host="127.0.0.1",
            port=args.port,
            reload=args.reload,
            reload_dirs=[str(API_DIR / "app")] if args.reload else None,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

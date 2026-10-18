"""开发启动前检查：不修改数据，不启动 Docker，不重置账号。"""

from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings


def main() -> int:
    settings = get_settings()
    engine = create_engine(settings.database_url, connect_args={"connect_timeout": 3})
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            current = MigrationContext.configure(connection).get_current_revision()
            scripts = ScriptDirectory.from_config(
                Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
            )
            if current != scripts.get_current_head():
                raise SystemExit("数据库迁移未完成，请先执行 pnpm db:migrate，再启动系统")
    except SQLAlchemyError:
        raise SystemExit(
            "数据库尚未就绪。请从系统菜单打开 Docker，执行 pnpm db:up 后重试；不会自动重置数据"
        ) from None
    finally:
        engine.dispose()
    # Agent 的生产依赖独立声明，本机可安装到共用开发解释器。
    try:
        import httpx  # noqa: F401
    except ImportError:
        raise SystemExit("缺少 Agent 依赖，请安装 apps/agent[dev] 后重试") from None
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

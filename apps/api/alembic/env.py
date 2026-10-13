"""Alembic 迁移环境。

两条约定：

1. 数据库连接串从应用配置读取，不在 alembic.ini 里重复维护一份。
2. `target_metadata` 取自 `app.db.registry`——只有在注册表里导入过的模型才会被
   autogenerate 感知，因此新增业务域时务必同步更新注册表。
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from app.core.config import get_settings

# 导入注册表即完成全部模型的注册，必须早于读取 target_metadata
from app.db.registry import Base
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 连接串可能含 % 号（转义过的密码），configparser 会做插值，必须先转义
config.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式：只渲染 SQL，不连接数据库。"""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：连接数据库执行迁移。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

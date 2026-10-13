"""数据库引擎与会话工厂。

引擎按需惰性创建：导入本模块不会连接数据库，因此导出 OpenAPI 文档、
运行不依赖数据库的测试都不需要数据库在线。
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        settings.database_url,
        echo=settings.db_echo,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
    )


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(
        bind=get_engine(),
        class_=Session,
        autoflush=False,
        expire_on_commit=False,
    )


def get_session() -> Iterator[Session]:
    """FastAPI 依赖：每个请求一个会话，异常回滚，结束必然关闭。"""
    session = get_session_factory()()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def dispose_engine() -> None:
    """应用关闭时释放连接池。"""
    if get_engine.cache_info().currsize:
        get_engine().dispose()
        get_engine.cache_clear()
        get_session_factory.cache_clear()

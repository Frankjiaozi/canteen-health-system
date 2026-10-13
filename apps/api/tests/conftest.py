"""测试夹具。

约定：

- `api_app` 是整个会话共用的应用实例。
- `client` 使用 `raise_server_exceptions=False`，让未预期异常也走全局异常处理器，
  这样测试断言的是真实对外行为（统一错误体），而不是被测试客户端重新抛出的异常。
- 依赖数据库的测试直接连本地开发库（由 `pnpm db:up` 提供），不另建测试库，
  以保证测试环境与 alembic 迁移、种子数据完全一致。
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from app.db.session import get_session_factory
from app.main import create_app
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


@pytest.fixture(scope="session")
def api_app() -> FastAPI:
    return create_app()


@pytest.fixture
def client(api_app: FastAPI) -> Iterator[TestClient]:
    test_client = TestClient(api_app, raise_server_exceptions=False)
    try:
        yield test_client
    finally:
        test_client.close()


@pytest.fixture
def db_session() -> Iterator[Session]:
    """数据库会话。

    测试结束时统一回滚，保证用例之间互不污染、也不会在开发库里留下垃圾数据。
    用例内部可以自由 `flush()`（以便触发约束校验），但不要 `commit()`。
    """
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.rollback()
        session.close()

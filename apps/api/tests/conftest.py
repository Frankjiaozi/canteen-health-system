"""测试夹具。

约定：

- `api_app` 是整个会话共用的应用实例。
- `client` 使用 `raise_server_exceptions=False`，让未预期异常也走全局异常处理器，
  这样测试断言的是真实对外行为（统一错误体），而不是被测试客户端重新抛出的异常。
- 依赖数据库的测试直接连本地开发库（由 `pnpm db:up` 提供），不另建测试库，
  以保证测试环境与 alembic 迁移、种子数据完全一致。
- **测试跑完会把库还原**：先记下基线主键，结束后删掉基线之外的行，再重灌一次种子。
  接口测试走的是真实提交（service 层自己 commit），不可能靠事务回滚，所以用「基线 + 还原」。
  没有这一步，跑几十轮之后开发库里会堆满测试造出来的菜品。
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

import pytest
from app.core.config import get_settings
from app.db import registry as _registry
from app.db import seed as seed_module
from app.db.session import get_session_factory
from app.main import create_app
from app.modules.nutrition import service as nutrition_service
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

#: 种子脚本内置的演示账号口令
DEMO_PASSWORD = "canteen@2026"


def login_as(api_client: TestClient, username: str) -> TestClient:
    """以指定演示账号登录，失败直接让用例报错。"""
    response = api_client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": DEMO_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return api_client


@pytest.fixture(scope="session", autouse=True)
def prepared_database() -> Iterator[None]:
    """把测试库备好，并在会话结束时还原。

    CI 上用的是空库、只跑了迁移，而公开大屏、看板、营养结果这几组用例都依赖
    「种子数据 + 营养计算结果」。缺了这一步，它们会以「查不到数据」的形式失败，
    报错信息完全看不出是环境问题——本地开发库里恰好留着历史数据，就把这个隐患盖住了。

    因此把「备数据」显式化：任何一次 pytest 都自带完整数据，不依赖外部手动步骤。
    种子脚本与营养计算都是幂等的，重复执行没有副作用。

    结束时的还原分两步，缺一不可：

    1. 删掉基线之外的行——测试新造的数据要清掉；
    2. 重灌一次种子——测试还会**改动**种子里的行（例如改配方、递增配方版本），
       只删新增行拉不回这些改动，而种子脚本是收敛的，重跑一遍就回到定义状态。
    """
    settings = get_settings()
    if settings.is_production:
        # 还原会删除数据，绝不能让它落到生产库上
        pytest.exit("拒绝在 production 环境上运行测试：会话结束时会清理测试数据", returncode=1)

    with get_session_factory()() as session:
        seed_module.run(session)
        nutrition_service.compute_recent_days(session, days=seed_module.HISTORY_DAYS)
        baseline = _baseline_ids(session)

    yield

    with get_session_factory()() as session:
        removed = _delete_rows_outside_baseline(session, baseline)
        seed_module.run(session)
        nutrition_service.compute_recent_days(session, days=seed_module.HISTORY_DAYS)
    if removed:
        print(f"\n[测试清理] 已删除 {removed} 行测试数据，并把种子数据还原到定义状态")


#: 删除顺序必须是「子表在前、父表在后」：菜品被配方、营养结果、菜单明细等
#: 以 RESTRICT 引用着，先删父表会被外键挡住。
_TEARDOWN_ORDER: tuple[type, ...] = (
    _registry.AssistantProposal,
    _registry.AssistantMessage,
    _registry.AssistantConversation,
    _registry.AuditLog,
    _registry.Feedback,
    _registry.DishNutrition,
    _registry.CalibrationFactor,
    _registry.Forecast,
    _registry.MenuSuggestion,
    _registry.DailyLogItem,
    _registry.MenuDayItem,
    _registry.RecipeItem,
    _registry.RecipeSeasoning,
    _registry.DailyLog,
    _registry.MenuDay,
    _registry.Dish,
    _registry.Ingredient,
    _registry.Seasoning,
    _registry.NutritionStandard,
    _registry.User,
)


def _baseline_ids(session: Session) -> dict[type, set[UUID]]:
    """记录每张表当前的主键，作为「测试之外的数据」的基线。"""
    return {
        model: set(session.scalars(select(model.id)).all())  # type: ignore[attr-defined]
        for model in _TEARDOWN_ORDER
    }


def _delete_rows_outside_baseline(session: Session, baseline: dict[type, set[UUID]]) -> int:
    removed = 0
    for model in _TEARDOWN_ORDER:
        known = baseline.get(model, set())
        # 基线为空表示这张表测试前本来就没有数据，那么现在里面的全要清掉。
        # 注意不能写成 id.not_in([])：SQLAlchemy 会把它渲染成恒真条件。
        statement = (
            delete(model) if not known else delete(model).where(model.id.not_in(known))  # type: ignore[attr-defined]
        )
        removed += session.execute(statement).rowcount or 0
    session.commit()
    return removed


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


@pytest.fixture
def as_recorder(client: TestClient) -> Iterator[TestClient]:
    """以食堂录入员身份登录。"""
    login_as(client, "recorder")
    yield client
    client.cookies.clear()


@pytest.fixture
def as_canteen_admin(client: TestClient) -> Iterator[TestClient]:
    """以食堂管理员身份登录。"""
    login_as(client, "canteen")
    yield client
    client.cookies.clear()


@pytest.fixture
def as_school_admin(client: TestClient) -> Iterator[TestClient]:
    """以学校管理方身份登录。"""
    login_as(client, "school")
    yield client
    client.cookies.clear()

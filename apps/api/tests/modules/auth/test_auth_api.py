"""认证接口的行为约定。

关键断言：登录失败与账号不存在返回同一提示（不可枚举账号）、
未登录 401、角色不符 403、Cookie 必须带 httpOnly。
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from app.core.errors import ForbiddenError, UnauthorizedError, register_exception_handlers
from app.core.security import create_access_token
from app.db.seed import DEFAULT_DEMO_PASSWORD, _stable_id
from app.modules.auth import repository, service
from app.modules.auth.dependencies import require_roles
from app.modules.auth.schemas import AuthUser
from app.shared.enums import UserRole
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

COOKIE_NAME = "canteen_token"


def _login(client: TestClient, username: str, password: str = DEFAULT_DEMO_PASSWORD):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


def test_login_succeeds_and_sets_httponly_cookie(client: TestClient) -> None:
    response = _login(client, "recorder")

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "recorder"
    assert body["role"] == UserRole.RECORDER.value
    assert body["role_label"] == "食堂录入员"

    set_cookie = response.headers["set-cookie"]
    assert COOKIE_NAME in set_cookie
    # 前端脚本必须拿不到令牌
    assert "httponly" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()
    # 响应体里绝不能出现口令或哈希
    assert "password" not in response.text


def test_wrong_password_is_rejected_with_401(client: TestClient) -> None:
    response = _login(client, "recorder", "definitely-wrong")

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"
    assert COOKIE_NAME not in response.headers.get("set-cookie", "")


def test_unknown_account_gives_the_same_message_as_wrong_password(client: TestClient) -> None:
    """两种失败必须不可区分，否则可以据此枚举系统里的账号。"""
    unknown = _login(client, "no-such-user", "whatever")
    wrong = _login(client, "recorder", "definitely-wrong")

    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["message"] == wrong.json()["message"]


def test_me_requires_login(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


def test_me_returns_current_user_after_login(client: TestClient) -> None:
    assert _login(client, "canteen").status_code == 200

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json()["username"] == "canteen"
    assert response.json()["role"] == UserRole.CANTEEN_ADMIN.value


def test_forged_cookie_is_rejected(client: TestClient) -> None:
    client.cookies.set(COOKIE_NAME, "not-a-real-token")

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401


def test_logout_clears_the_cookie(client: TestClient) -> None:
    assert _login(client, "recorder").status_code == 200

    response = client.post("/api/v1/auth/logout")

    assert response.status_code == 204
    assert f'{COOKIE_NAME}=""' in response.headers["set-cookie"]


# ---------------------------------------------------------------------------
# 角色校验
# ---------------------------------------------------------------------------
def _build_guarded_app() -> FastAPI:
    """用一个只挂角色的最小应用验证 403 路径，避免为测试往线上接口里塞调试路由。"""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/recorder-only")
    def _recorder_only(
        user: AuthUser = Depends(require_roles(UserRole.RECORDER)),
    ) -> dict[str, str]:
        return {"username": user.username}

    @app.get("/any-role")
    def _any_role(
        user: AuthUser = Depends(
            require_roles(UserRole.RECORDER, UserRole.CANTEEN_ADMIN, UserRole.SCHOOL_ADMIN)
        ),
    ) -> dict[str, str]:
        return {"username": user.username}

    return app


@pytest.fixture(scope="module")
def guarded_client() -> Iterator[TestClient]:
    test_client = TestClient(_build_guarded_app(), raise_server_exceptions=False)
    try:
        yield test_client
    finally:
        test_client.close()


def _cookie_for(username: str, role: UserRole) -> dict[str, str]:
    token = create_access_token(user_id=_stable_id("user", username), username=username, role=role)
    return {COOKIE_NAME: token}


def test_role_mismatch_returns_403(guarded_client: TestClient) -> None:
    guarded_client.cookies.update(_cookie_for("school", UserRole.SCHOOL_ADMIN))

    response = guarded_client.get("/recorder-only")

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


def test_matching_role_passes(guarded_client: TestClient) -> None:
    guarded_client.cookies.update(_cookie_for("recorder", UserRole.RECORDER))

    response = guarded_client.get("/recorder-only")

    assert response.status_code == 200
    assert response.json()["username"] == "recorder"


def test_any_allowed_role_passes(guarded_client: TestClient) -> None:
    guarded_client.cookies.update(_cookie_for("school", UserRole.SCHOOL_ADMIN))

    assert guarded_client.get("/any-role").status_code == 200


def test_missing_cookie_returns_401_on_guarded_route(guarded_client: TestClient) -> None:
    guarded_client.cookies.clear()

    response = guarded_client.get("/recorder-only")

    assert response.status_code == 401


def test_token_of_deleted_account_is_rejected(guarded_client: TestClient) -> None:
    """令牌里的 sub 必须能在库中找到对应账号，否则一律视为未登录。"""
    guarded_client.cookies.update(_cookie_for(str(uuid4()), UserRole.RECORDER))

    response = guarded_client.get("/recorder-only")

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# 服务层规则
# ---------------------------------------------------------------------------
def test_inactive_account_is_rejected(db_session: Session) -> None:
    user = repository.get_by_username(db_session, "recorder")
    assert user is not None
    user.is_active = False
    db_session.flush()

    with pytest.raises(ForbiddenError):
        service.authenticate(db_session, "recorder", DEFAULT_DEMO_PASSWORD)


def test_unknown_account_raises_unauthorized(db_session: Session) -> None:
    with pytest.raises(UnauthorizedError):
        service.authenticate(db_session, "no-such-user", "whatever")

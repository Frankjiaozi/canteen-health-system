"""开放注册的真实数据库验证；每个用例在外层事务中回滚。"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest
from app.core.security import verify_password
from app.db.session import get_engine, get_session
from app.main import create_app
from app.modules.auth import repository
from app.modules.auth.models import User
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session


@pytest.fixture
def registration_client() -> Iterator[tuple[TestClient, Session]]:
    connection = get_engine().connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    app = create_app()

    def override_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


def payload() -> dict[str, str]:
    return {
        "username": f"signup_{uuid4().hex[:16]}",
        "display_name": "测试录入员",
        "password": "TestPass2026",
    }


def test_registration_login_logout_lifecycle(
    registration_client: tuple[TestClient, Session],
) -> None:
    client, session = registration_client
    values = payload()
    values["username"] = f"  {values['username'].upper()}  "
    values["display_name"] = "  测试录入员  "
    response = client.post("/api/v1/auth/register", json=values)
    assert response.status_code == 201, response.text
    user = response.json()
    assert user["username"] == values["username"].strip().lower()
    assert user["display_name"] == "测试录入员"
    assert user["role"] == "RECORDER"
    assert user["role_label"] == "食堂录入员"
    assert "password" not in response.text
    assert "httponly" in response.headers["set-cookie"].lower()
    stored = session.scalar(select(User).where(User.username == user["username"]))
    assert stored is not None
    assert stored.password_hash != values["password"]
    assert verify_password(values["password"], stored.password_hash)
    assert stored.last_login_at is not None
    assert client.get("/api/v1/auth/me").json()["id"] == user["id"]
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login",
            json={
                "username": values["username"],
                "password": values["password"],
            },
        ).status_code
        == 200
    )


def test_duplicate_username_preserves_existing_password(
    registration_client: tuple[TestClient, Session],
) -> None:
    client, _ = registration_client
    values = payload()
    assert client.post("/api/v1/auth/register", json=values).status_code == 201
    duplicate = {**values, "username": values["username"].upper(), "password": "OtherPass2026"}
    response = client.post("/api/v1/auth/register", json=duplicate)
    assert response.status_code == 409
    assert response.json()["message"] == "该登录名已被使用，请换一个"
    assert (
        client.post(
            "/api/v1/auth/login",
            json={
                "username": values["username"],
                "password": values["password"],
            },
        ).status_code
        == 200
    )


@pytest.mark.parametrize("role", ["CANTEEN_ADMIN", "SCHOOL_ADMIN"])
def test_registration_cannot_choose_privileged_role(
    registration_client: tuple[TestClient, Session],
    role: str,
) -> None:
    client, session = registration_client
    values = {**payload(), "role": role}
    assert client.post("/api/v1/auth/register", json=values).status_code == 422
    assert session.scalar(select(User).where(User.username == str(values["username"]))) is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("username", "ab"),
        ("username", "invalid-name"),
        ("username", " " * 4),
        ("display_name", "   "),
        ("display_name", "测试\n账号"),
        ("password", "abc123"),
        ("password", "12345678"),
        ("password", "abcdefgh"),
        ("password", "密" * 24 + "a1"),
        ("username", None),
        ("username", 1234),
        ("password", 12345678),
    ],
)
def test_invalid_registration_does_not_create_account(
    registration_client: tuple[TestClient, Session],
    field: str,
    value: Any,
) -> None:
    client, session = registration_client
    values = {**payload(), field: value}
    response = client.post("/api/v1/auth/register", json=values)
    assert response.status_code == 422, response.text
    assert "set-cookie" not in response.headers
    assert session.scalar(select(User).where(User.username == str(values["username"]))) is None


def test_registration_supports_password_at_bcrypt_byte_limit(
    registration_client: tuple[TestClient, Session],
) -> None:
    client, _ = registration_client
    values = {**payload(), "password": "密" * 23 + "a12"}
    assert len(values["password"].encode("utf-8")) == 72
    response = client.post("/api/v1/auth/register", json=values)
    assert response.status_code == 201, response.text


def test_duplicate_race_returns_conflict_and_session_recovers(
    registration_client: tuple[TestClient, Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = registration_client
    values = payload()
    assert client.post("/api/v1/auth/register", json=values).status_code == 201
    monkeypatch.setattr(repository, "get_by_username", lambda *_: None)
    response = client.post("/api/v1/auth/register", json=values)
    assert response.status_code == 409, response.text
    assert client.post("/api/v1/auth/register", json=payload()).status_code == 201

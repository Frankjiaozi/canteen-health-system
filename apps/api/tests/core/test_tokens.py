"""访问令牌的签发与校验。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from app.core.config import get_settings
from app.core.security import TokenError, create_access_token, decode_access_token
from app.shared.enums import UserRole


def test_roundtrip_keeps_subject_username_and_role() -> None:
    user_id = uuid4()
    token = create_access_token(user_id=user_id, username="recorder", role=UserRole.RECORDER)

    claims = decode_access_token(token)

    assert claims.user_id == user_id
    assert claims.username == "recorder"
    assert claims.role is UserRole.RECORDER


def test_tampered_token_is_rejected() -> None:
    token = create_access_token(user_id=uuid4(), username="recorder", role=UserRole.RECORDER)
    tampered = f"{token[:-4]}AAAA"

    with pytest.raises(TokenError):
        decode_access_token(tampered)


def test_token_signed_with_another_secret_is_rejected() -> None:
    forged = jwt.encode(
        {
            "sub": str(uuid4()),
            "username": "attacker",
            "role": UserRole.SCHOOL_ADMIN.value,
            "exp": datetime.now(tz=UTC) + timedelta(hours=1),
        },
        "a-completely-different-secret-that-is-long-enough",
        algorithm="HS256",
    )

    with pytest.raises(TokenError):
        decode_access_token(forged)


def test_expired_token_is_rejected() -> None:
    settings = get_settings()
    expired = jwt.encode(
        {
            "sub": str(uuid4()),
            "username": "recorder",
            "role": UserRole.RECORDER.value,
            "exp": datetime.now(tz=UTC) - timedelta(minutes=1),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(TokenError):
        decode_access_token(expired)


def test_token_with_unknown_role_is_rejected() -> None:
    settings = get_settings()
    bogus = jwt.encode(
        {
            "sub": str(uuid4()),
            "username": "recorder",
            "role": "SUPER_ADMIN",
            "exp": datetime.now(tz=UTC) + timedelta(hours=1),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(TokenError):
        decode_access_token(bogus)

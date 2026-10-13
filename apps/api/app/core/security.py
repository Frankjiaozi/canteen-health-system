"""密码与令牌安全。

密码哈希用 pwdlib（bcrypt 后端）。刻意不用 passlib：该项目已停止维护，
且与 bcrypt 5.x 不兼容（读取 `bcrypt.__about__` 会直接抛错）。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import NamedTuple
from uuid import UUID

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher

from app.core.config import get_settings
from app.shared.enums import UserRole

# 显式指定 bcrypt：不用 PasswordHash.recommended()，避免运行环境里装了 argon2 时
# 哈希算法无声漂移，导致不同机器的口令库不通用
_password_hasher = PasswordHash((BcryptHasher(),))


def hash_password(plain_password: str) -> str:
    """生成口令哈希。同一口令每次结果不同（自带随机盐）。"""
    return _password_hasher.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """校验口令。哈希格式非法时返回 False，不抛异常。"""
    try:
        return _password_hasher.verify(plain_password, password_hash)
    except Exception:
        return False


class TokenError(Exception):
    """令牌不可用：过期、签名不符、格式错误或内容不完整。"""


class TokenClaims(NamedTuple):
    """已校验的令牌内容。"""

    user_id: UUID
    username: str
    role: UserRole


def create_access_token(*, user_id: UUID, username: str, role: UserRole) -> str:
    """签发访问令牌。

    令牌只承载「你是谁」，不承载权限明细——权限判断始终以数据库中的当前角色为准，
    这样管理员改角色后无需等令牌过期即刻生效。
    """
    settings = get_settings()
    issued_at = datetime.now(tz=UTC)
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role.value,
        "iat": issued_at,
        "exp": issued_at + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> TokenClaims:
    """校验并解析访问令牌，失败一律抛 `TokenError`。"""
    settings = get_settings()
    try:
        raw = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise TokenError("登录已过期，请重新登录") from exc

    try:
        return TokenClaims(
            user_id=UUID(raw["sub"]),
            username=raw["username"],
            role=UserRole(raw["role"]),
        )
    except (KeyError, ValueError) as exc:
        raise TokenError("登录凭证格式不正确") from exc

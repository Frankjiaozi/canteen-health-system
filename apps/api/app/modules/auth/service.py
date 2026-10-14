"""认证业务规则。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ConflictError, ForbiddenError, UnauthorizedError
from app.core.security import hash_password, verify_password
from app.modules.auth import repository
from app.modules.auth.models import User
from app.modules.auth.schemas import AuthUser, RegisterRequest
from app.shared.enums import UserRole

USERNAME_TAKEN = "该登录名已被使用，请换一个"


def register(session: Session, payload: RegisterRequest) -> User:
    if repository.get_by_username(session, payload.username) is not None:
        raise ConflictError(USERNAME_TAKEN)
    user = User(
        username=payload.username,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
        role=UserRole.RECORDER,
        is_active=True,
    )
    try:
        return repository.create(session, user)
    except IntegrityError as exc:
        # 并发注册可能在预检查后撞上唯一约束，仍返回可读的重名提示。
        session.rollback()
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint == "uq_users_username":
            raise ConflictError(USERNAME_TAKEN) from exc
        raise


def to_auth_user(user: User) -> AuthUser:
    return AuthUser(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        role_label=user.role.label,
    )


def authenticate(session: Session, username: str, password: str) -> User:
    """按用户名与口令校验身份。

    账号不存在与口令错误返回**完全相同**的提示，避免通过错误信息枚举出系统里有哪些账号。
    """
    user = repository.get_by_username(session, username)
    if user is None or not verify_password(password, user.password_hash):
        raise UnauthorizedError("用户名或密码不正确")
    if not user.is_active:
        # 只有口令正确才会走到这里，因此不会泄露账号是否存在
        raise ForbiddenError("账号已停用，请联系管理员")
    return user


def record_login(session: Session, user: User) -> None:
    settings = get_settings()
    repository.mark_login(session, user, datetime.now(settings.timezone))

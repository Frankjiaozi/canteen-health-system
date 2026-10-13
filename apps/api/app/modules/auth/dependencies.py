"""认证相关的 FastAPI 依赖。

认证是横切关注点：本模块是全项目**唯一**允许被其它业务域 import 的依赖模块。
业务域通过 `Depends(require_roles(...))` 拿到 `AuthUser` 值对象，
既完成鉴权，也不必接触 `auth` 域的 ORM 模型。
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.security import TokenError, decode_access_token
from app.db.session import get_session
from app.modules.auth import repository, service
from app.modules.auth.schemas import AuthUser
from app.shared.enums import UserRole


def get_current_user(
    request: Request,
    session: Session = Depends(get_session),
) -> AuthUser:
    """从 httpOnly Cookie 中读取令牌并解析出当前用户。"""
    settings = get_settings()
    token = request.cookies.get(settings.cookie_name)
    if not token:
        raise UnauthorizedError()

    try:
        claims = decode_access_token(token)
    except TokenError as exc:
        raise UnauthorizedError(str(exc)) from exc

    # 角色与启停状态以数据库为准，而不是信任令牌里的快照
    user = repository.get_by_id(session, claims.user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("账号不存在或已停用")
    return service.to_auth_user(user)


def require_roles(*allowed: UserRole) -> Callable[[AuthUser], AuthUser]:
    """生成角色校验依赖。

    用法：`user: AuthUser = Depends(require_roles(UserRole.RECORDER, UserRole.CANTEEN_ADMIN))`
    """

    def _dependency(current_user: AuthUser = Depends(get_current_user)) -> AuthUser:
        if current_user.role not in allowed:
            raise ForbiddenError()
        return current_user

    return _dependency

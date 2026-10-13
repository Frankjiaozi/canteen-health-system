"""认证接口：登录、退出、当前用户。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token
from app.db.session import get_session
from app.modules.auth import service
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.schemas import AuthUser, LoginRequest

router = APIRouter(prefix="/auth", tags=["认证"])


def _set_auth_cookie(response: Response, token: str) -> None:
    """把令牌写进 httpOnly Cookie。

    前端代码拿不到令牌本身，脚本注入也就无法窃取登录态。
    `SameSite=Lax` 让跨站发起的 POST 不携带该 Cookie，是当前场景下够用的 CSRF 防护。
    """
    settings = get_settings()
    response.set_cookie(
        key=settings.cookie_name,
        value=token,
        max_age=settings.jwt_expire_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post("/login", response_model=AuthUser, summary="登录")
def login(
    payload: LoginRequest,
    response: Response,
    session: Session = Depends(get_session),
) -> AuthUser:
    user = service.authenticate(session, payload.username, payload.password)
    service.record_login(session, user)
    session.commit()

    token = create_access_token(user_id=user.id, username=user.username, role=user.role)
    _set_auth_cookie(response, token)
    return service.to_auth_user(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="退出登录")
def logout(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(key=settings.cookie_name, path="/")


@router.get("/me", response_model=AuthUser, summary="当前登录用户")
def me(current_user: AuthUser = Depends(get_current_user)) -> AuthUser:
    return current_user

"""认证域的请求与响应模型。"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.shared.enums import UserRole


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64, description="登录名")
    password: str = Field(min_length=1, max_length=128, description="口令")


class AuthUser(BaseModel):
    """对外暴露的当前用户。

    刻意不直接返回 ORM 模型：其它业务域拿到的是这个值对象，
    因此不会（也不该）去引用 `auth` 域的模型定义。
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    display_name: str
    role: UserRole
    # 中文展示名随响应一起下发，前端不必再维护一份角色文案映射
    role_label: str

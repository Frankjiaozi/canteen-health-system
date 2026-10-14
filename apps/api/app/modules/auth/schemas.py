"""认证域的请求与响应模型。"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.shared.enums import UserRole


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64, description="登录名")
    password: str = Field(min_length=1, max_length=128, description="口令")

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value: Any) -> Any:
        return value.strip().lower() if isinstance(value, str) else value


class RegisterRequest(BaseModel):
    """开放注册仅接收基本资料，角色由服务端指定。"""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(
        min_length=3,
        max_length=32,
        pattern=r"^[a-z0-9_]{3,32}$",
        description="登录名，3–32 位字母、数字或下划线，不区分大小写",
    )
    display_name: str = Field(min_length=1, max_length=64, description="显示名称")
    password: str = Field(min_length=8, max_length=72, description="密码，包含字母和数字")

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value: Any) -> Any:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        name = value.strip()
        if not name or not name.isprintable():
            raise ValueError("显示名称不能为空，也不能包含换行等控制字符")
        return name

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("密码的 UTF-8 长度不能超过 72 字节")
        if not any(char.isalpha() for char in value) or not any(char.isdigit() for char in value):
            raise ValueError("密码必须同时包含字母和数字")
        return value


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

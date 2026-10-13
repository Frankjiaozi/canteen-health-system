"""账号模型。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import enum_check, enum_type
from app.shared.enums import UserRole


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """系统账号。

    仅三类可登录角色：食堂录入员、食堂管理员、学校管理方。
    系统内**没有学生账号**——需求文档中的「学生端」对应的是免登录的公开大屏。
    """

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[UserRole] = mapped_column(enum_type(UserRole), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (enum_check("role", UserRole),)

    def __repr__(self) -> str:
        return f"<User {self.username} role={self.role}>"

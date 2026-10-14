"""账号数据访问。

只做查询与持久化，不含业务规则。
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.models import User


def get_by_username(session: Session, username: str) -> User | None:
    return session.scalar(select(User).where(User.username == username))


def get_by_id(session: Session, user_id: UUID) -> User | None:
    return session.get(User, user_id)


def create(session: Session, user: User) -> User:
    session.add(user)
    session.flush()
    return user


def mark_login(session: Session, user: User, moment: datetime) -> None:
    user.last_login_at = moment
    session.flush()

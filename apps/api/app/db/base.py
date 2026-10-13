"""SQLAlchemy 声明基类与通用 Mixin。

三条全项目统一的约定：

1. **约束命名规则**：显式声明 naming_convention，保证 Alembic 生成的迁移可稳定回滚。
2. **主键统一 UUID**：由应用层生成（非数据库自增），使离线录入重放与跨端同步天然幂等。
3. **时间戳统一 timestamptz**：绝不用区域无关的 naive datetime。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# 枚举字段统一用 VARCHAR + CHECK 约束，而不是 PostgreSQL 原生枚举：
# 后者每次增删取值都要 ALTER TYPE，在需要迁移与回滚的场景里代价过高。
ENUM_VARCHAR_LENGTH = 32


class Base(DeclarativeBase):
    """全项目唯一的声明基类。"""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPrimaryKeyMixin:
    """UUID 主键。应用层生成，便于离线场景提前确定标识。"""

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    """创建与更新时间，均由数据库侧 `now()` 维护。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

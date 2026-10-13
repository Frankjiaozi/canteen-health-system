"""SQLAlchemy 列类型工具。"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import CheckConstraint
from sqlalchemy import Enum as SAEnum

from app.db.base import ENUM_VARCHAR_LENGTH

_CAMEL_TO_SNAKE = re.compile(r"(?<!^)(?=[A-Z])")


def enum_type(enum_cls: type[Any], *, length: int = ENUM_VARCHAR_LENGTH) -> SAEnum:
    """把 Python 字符串枚举映射成 VARCHAR + CHECK 约束的列类型。

    刻意不用 PostgreSQL 原生 ENUM：原生的每增删一个取值都要 `ALTER TYPE`，
    在需要可回滚迁移与离线同步的项目里成本过高。CHECK 约束同样能保证数据库层
    完整性，扩展时只需改约束。

    注意：这里固定 `create_constraint=False`，取值约束改由 `enum_check()` 显式声明。
    原因是 Enum 属于 SQLAlchemy 的 SchemaType，开启 create_constraint 会在**表级与
    metadata 级各注册一条**约束，生成的迁移里会出现两条一模一样的 CHECK。
    """
    name = _CAMEL_TO_SNAKE.sub("_", enum_cls.__name__).lower()
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=False,
        validate_strings=True,
        length=length,
    )


def enum_check(column_name: str, enum_cls: type[Any]) -> CheckConstraint:
    """生成枚举列的取值约束，放进 `__table_args__` 使用。"""
    values = ", ".join(f"'{member.value}'" for member in enum_cls)
    return CheckConstraint(f"{column_name} IN ({values})", name=f"{column_name}_valid")

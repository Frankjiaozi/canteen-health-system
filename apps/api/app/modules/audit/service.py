"""审计留痕服务。

其它业务域在改动关键数据时调用 `record()`。这里刻意不接收 `AuthUser` 值对象，
只收操作人的标识与姓名——审计不该反向依赖认证域。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.modules.audit.models import AuditLog
from app.shared.enums import AuditAction

logger = get_logger(__name__)


def record(
    session: Session,
    *,
    entity_type: str,
    entity_id: UUID | str,
    action: AuditAction,
    actor_id: UUID | None = None,
    actor_name: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    note: str | None = None,
) -> AuditLog:
    """写一条留痕。不提交事务，由调用方决定何时提交。"""
    entry = AuditLog(
        entity_type=entity_type,
        entity_id=str(entity_id),
        action=action,
        actor_id=actor_id,
        # 冗余保存姓名：账号被停用或删除后，历史留痕仍要能看懂是谁做的
        actor_name=actor_name,
        before=before,
        after=after,
        note=note,
    )
    session.add(entry)
    return entry

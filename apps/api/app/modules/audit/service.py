"""审计留痕服务。

其它业务域在改动关键数据时调用 `record()`。这里刻意不接收 `AuthUser` 值对象，
只收操作人的标识与姓名——审计不该反向依赖认证域。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
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


def has_change_after(session: Session, *, entity_id: UUID | str, since: datetime) -> bool:
    """这条数据在 `since` 之后有没有被改过。

    「撤回」靠它守一条底线：如果同一条数据在执行之后又被别人改过，
    撤回就会把那次改动一起抹掉。宁可拒绝撤回并让人手工核对，也不要悄悄覆盖别人的活。
    """
    total = session.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.entity_id == str(entity_id), AuditLog.created_at > since)
    )
    return bool(total)

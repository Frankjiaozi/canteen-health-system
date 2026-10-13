"""食材库的权限边界与操作留痕。"""

from __future__ import annotations

from app.modules.audit.models import AuditLog
from app.shared.enums import AuditAction
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from .conftest import BASE, new_ingredient_payload


def test_school_admin_can_read(as_school_admin: TestClient) -> None:
    assert as_school_admin.get(BASE).status_code == 200


def test_school_admin_cannot_create(as_school_admin: TestClient) -> None:
    response = as_school_admin.post(BASE, json=new_ingredient_payload())

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


def test_school_admin_cannot_modify_or_delete(as_school_admin: TestClient) -> None:
    ingredient_id = as_school_admin.get(BASE).json()["items"][0]["id"]

    assert as_school_admin.patch(f"{BASE}/{ingredient_id}", json={"note": "x"}).status_code == 403
    assert as_school_admin.delete(f"{BASE}/{ingredient_id}").status_code == 403


def test_anonymous_cannot_write(client: TestClient) -> None:
    assert client.post(BASE, json=new_ingredient_payload()).status_code == 401


def test_canteen_admin_can_write(client: TestClient) -> None:
    from .conftest import login

    login(client, "canteen")
    try:
        assert client.post(BASE, json=new_ingredient_payload()).status_code == 201
    finally:
        client.cookies.clear()


def test_create_update_and_deactivate_are_audited(
    as_recorder: TestClient, db_session: Session
) -> None:
    """新建、修改、停用都要留下操作人与前后值。"""
    created = as_recorder.post(BASE, json=new_ingredient_payload()).json()
    as_recorder.patch(f"{BASE}/{created['id']}", json={"note": "补充说明"})
    as_recorder.delete(f"{BASE}/{created['id']}")

    entries = list(
        db_session.scalars(
            select(AuditLog)
            .where(AuditLog.entity_type == "ingredient", AuditLog.entity_id == created["id"])
            .order_by(AuditLog.created_at)
        )
    )

    assert [entry.action for entry in entries] == [
        AuditAction.CREATE,
        AuditAction.UPDATE,
        AuditAction.DELETE,
    ]
    assert all(entry.actor_name for entry in entries)
    assert entries[0].actor_name == "王芳（录入员）"
    assert entries[1].before != entries[1].after


def test_no_op_update_does_not_create_audit_noise(
    as_recorder: TestClient, db_session: Session
) -> None:
    """提交了内容但什么都没变，不该留下一条无意义的修改记录。"""
    created = as_recorder.post(BASE, json=new_ingredient_payload()).json()

    as_recorder.patch(f"{BASE}/{created['id']}", json={"note": created["note"]})

    updates = list(
        db_session.scalars(
            select(AuditLog).where(
                AuditLog.entity_id == created["id"],
                AuditLog.action == AuditAction.UPDATE,
            )
        )
    )
    assert updates == []

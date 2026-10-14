"""调味料库接口：与食材库同一套约定，重点验权限、软删与留痕。"""

from __future__ import annotations

from uuid import uuid4

from app.modules.audit.models import AuditLog
from app.modules.seasoning.models import Seasoning
from app.shared.enums import AuditAction, SeasoningCategory
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

BASE = "/api/v1/seasonings"


def _payload(name: str | None = None) -> dict[str, object]:
    return {
        "name": name or f"测试调味料-{uuid4().hex[:8]}",
        "category": SeasoningCategory.OTHER.value,
        "unit": "g",
        "energy_kcal": "120.5",
        "sodium_mg": "3000.00",
        "unit_price": "9.50",
        "data_source": "接口测试构造",
    }


def test_list_requires_login(client: TestClient) -> None:
    assert client.get(BASE).status_code == 401


def test_seeded_seasonings_are_listed(as_recorder: TestClient) -> None:
    body = as_recorder.get(BASE, params={"page_size": 100}).json()

    names = {item["name"] for item in body["items"]}
    assert {"食盐", "大豆油", "白砂糖", "生抽酱油", "豆瓣酱", "陈醋"} <= names


def test_create_update_and_deactivate(as_recorder: TestClient, db_session: Session) -> None:
    created = as_recorder.post(BASE, json=_payload()).json()
    assert created["category_label"] == "其他"
    assert created["energy_kcal"] == "120.50"

    updated = as_recorder.patch(f"{BASE}/{created['id']}", json={"sodium_mg": "1.10"})
    assert updated.status_code == 200
    assert updated.json()["sodium_mg"] == "1.10"
    assert updated.json()["energy_kcal"] == created["energy_kcal"]

    removed = as_recorder.delete(f"{BASE}/{created['id']}")
    assert removed.status_code == 200
    assert removed.json()["is_active"] is False
    assert as_recorder.get(BASE, params={"keyword": created["name"]}).json()["total"] == 0

    stored = db_session.get(Seasoning, created["id"])
    assert stored is not None and stored.is_active is False


def test_duplicate_name_is_rejected(as_recorder: TestClient) -> None:
    payload = _payload()
    assert as_recorder.post(BASE, json=payload).status_code == 201

    duplicate = as_recorder.post(BASE, json=payload)

    assert duplicate.status_code == 409
    assert "已存在" in duplicate.json()["message"]


def test_update_unknown_returns_404(as_recorder: TestClient) -> None:
    assert as_recorder.patch(f"{BASE}/{uuid4()}", json={"note": "x"}).status_code == 404


def test_school_admin_is_read_only(as_school_admin: TestClient) -> None:
    assert as_school_admin.get(BASE).status_code == 200
    assert as_school_admin.post(BASE, json=_payload()).status_code == 403


def test_changes_are_audited(as_recorder: TestClient, db_session: Session) -> None:
    created = as_recorder.post(BASE, json=_payload()).json()
    as_recorder.patch(f"{BASE}/{created['id']}", json={"note": "补充"})
    as_recorder.delete(f"{BASE}/{created['id']}")

    entries = list(
        db_session.scalars(
            select(AuditLog)
            .where(AuditLog.entity_type == "seasoning", AuditLog.entity_id == created["id"])
            .order_by(AuditLog.created_at)
        )
    )

    assert [entry.action for entry in entries] == [
        AuditAction.CREATE,
        AuditAction.UPDATE,
        AuditAction.DELETE,
    ]
    assert all(entry.actor_name for entry in entries)

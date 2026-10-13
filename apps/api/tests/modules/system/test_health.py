"""健康检查与请求上下文的接口测试。

`/health/db` 需要真实 PostgreSQL（`pnpm db:up` 提供）。
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_reports_app_metadata(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app_name"] == "食堂健康管理系统"
    assert body["timezone"] == "Asia/Shanghai"
    # 服务器时间必须带时区偏移，避免前端拿到区域无关时间
    assert body["server_time"].endswith("+08:00")


def test_health_db_connects_to_real_postgres(client: TestClient) -> None:
    response = client.get("/health/db")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["server_version"].startswith("PostgreSQL")
    assert body["latency_ms"] >= 0


def test_every_response_carries_request_id(client: TestClient) -> None:
    response = client.get("/health")

    assert response.headers.get("X-Request-ID")


def test_upstream_request_id_is_preserved(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "trace-me-123"})

    assert response.headers.get("X-Request-ID") == "trace-me-123"

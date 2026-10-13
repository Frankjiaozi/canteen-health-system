"""统一错误响应的契约测试。

这里保护的是对外契约：任何失败路径都必须返回 `{code, message, details}`，
且未预期异常不得把内部细节泄露到响应体。
"""

from __future__ import annotations

import pytest
from app.core.errors import BusinessRuleError, NotFoundError, register_exception_handlers
from fastapi import FastAPI, Query
from fastapi.testclient import TestClient


def _build_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/not-found")
    def _raise_not_found() -> None:
        raise NotFoundError("食材不存在", details={"field": "id"})

    @app.get("/rule-violated")
    def _raise_rule_violated() -> None:
        raise BusinessRuleError("当日记录已提交，不能重复提交")

    @app.get("/boom")
    def _raise_unexpected() -> None:
        raise RuntimeError("内部细节不应出现在响应体里")

    @app.get("/validated")
    def _validated(limit: int = Query(ge=1)) -> dict[str, int]:
        return {"limit": limit}

    return app


@pytest.fixture(scope="module")
def error_client() -> TestClient:
    return TestClient(_build_app(), raise_server_exceptions=False)


def test_app_error_keeps_status_code_and_details(error_client: TestClient) -> None:
    response = error_client.get("/not-found")

    assert response.status_code == 404
    assert response.json() == {
        "code": "not_found",
        "message": "食材不存在",
        "details": {"field": "id"},
    }


def test_business_rule_error_maps_to_422(error_client: TestClient) -> None:
    response = error_client.get("/rule-violated")

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "business_rule_violated"
    assert body["message"] == "当日记录已提交，不能重复提交"


def test_unexpected_error_returns_generic_body_without_leaking_details(
    error_client: TestClient,
) -> None:
    response = error_client.get("/boom")

    assert response.status_code == 500
    assert response.json() == {
        "code": "internal_error",
        "message": "服务器内部错误",
        "details": None,
    }
    assert "内部细节" not in response.text


def test_validation_error_lists_field_reasons(error_client: TestClient) -> None:
    response = error_client.get("/validated", params={"limit": 0})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert body["message"] == "请求参数校验失败"
    assert body["details"][0]["field"] == "limit"


def test_unknown_route_returns_localized_structured_404(error_client: TestClient) -> None:
    response = error_client.get("/definitely-not-here")

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "not_found"
    # Starlette 默认的英文 "Not Found" 必须换成中文，界面不能漏英文
    assert body["message"] == "请求的资源不存在"

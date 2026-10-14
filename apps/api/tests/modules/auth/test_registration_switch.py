"""自助注册开关。

演示环境开放注册（访客可自行注册录入员账号）；学校内网正式部署必须关掉——
注册出来的账号带写权限，而配方库是全系统最需要人工投入、也最不能出错的数据。
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator

import pytest
from app.core.config import get_settings
from fastapi.testclient import TestClient

REGISTER = "/api/v1/auth/register"

_BASE_PAYLOAD = {
    "username": "switch_probe_user",
    "display_name": "开关探针",
    "password": "probe12345",
}


@pytest.fixture
def set_registration_switch() -> Iterator[Callable[[str], None]]:
    """临时拨动开关，用完复位。

    设置是进程内单例缓存的，因此改完环境变量必须清缓存才会被重新读取。
    """

    def _set(value: str) -> None:
        os.environ["ALLOW_OPEN_REGISTRATION"] = value
        get_settings.cache_clear()

    yield _set
    os.environ.pop("ALLOW_OPEN_REGISTRATION", None)
    get_settings.cache_clear()


def test_register_is_forbidden_with_an_actionable_message(
    client: TestClient, set_registration_switch: Callable[[str], None]
) -> None:
    set_registration_switch("false")

    response = client.post(REGISTER, json=_BASE_PAYLOAD)

    assert response.status_code == 403
    body = response.json()
    assert body["code"] == "forbidden"
    # 不能只丢一个 403，要让人知道下一步该做什么
    assert "请找管理员开通" in body["message"]
    assert "set-cookie" not in {key.lower() for key in response.headers}


def test_disabled_switch_does_not_create_the_account(
    client: TestClient, set_registration_switch: Callable[[str], None]
) -> None:
    set_registration_switch("false")
    client.post(REGISTER, json=_BASE_PAYLOAD)

    login = client.post(
        "/api/v1/auth/login",
        json={"username": _BASE_PAYLOAD["username"], "password": _BASE_PAYLOAD["password"]},
    )

    assert login.status_code == 401, "开关关着时连账号都不该建出来"


def test_switch_on_allows_registration(
    client: TestClient, set_registration_switch: Callable[[str], None]
) -> None:
    set_registration_switch("true")

    response = client.post(REGISTER, json={**_BASE_PAYLOAD, "username": "switch_probe_open"})

    assert response.status_code == 201
    assert response.json()["role"] == "RECORDER"

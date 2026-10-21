from __future__ import annotations

from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from app.core.config import get_settings
from app.modules.dish.images import MAX_IMAGE_BYTES
from fastapi.testclient import TestClient
from PIL import Image


@pytest.fixture(autouse=True)
def isolated_images(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "dish_image_dir", tmp_path)


def picture() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (48, 32), "#819477").save(stream, "PNG")
    return stream.getvalue()


def test_upload_replace_delete_and_list_metadata(as_recorder: TestClient) -> None:
    dish = as_recorder.get("/api/v1/dishes").json()["items"][0]
    path = f"/api/v1/dishes/{dish['id']}/image"
    assert dish["image_url"] is None
    assert as_recorder.get(path).status_code == 404
    response = as_recorder.put(path, files={"file": ("../../outside.png", picture(), "image/png")})
    assert response.status_code == 200, response.text
    assert response.json()["image_url"].startswith(path + "?v=")
    downloaded = as_recorder.get(response.json()["image_url"])
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"] == "image/webp"
    with Image.open(BytesIO(downloaded.content)) as saved:
        assert saved.size == (48, 32)
    assert as_recorder.get(f"/api/v1/dishes/{dish['id']}").json()["image_url"]
    version = response.json()["image_url"]
    assert (
        as_recorder.put(path, files={"file": ("new.png", picture(), "image/png")}).json()[
            "image_url"
        ]
        != version
    )
    assert as_recorder.delete(path).json()["image_url"] is None
    assert as_recorder.get(path).status_code == 404


@pytest.mark.parametrize(
    "content,mime",
    [
        (b"not-an-image", "image/png"),
        (b"<svg/>", "image/svg+xml"),
        (b"x" * (MAX_IMAGE_BYTES + 1), "image/jpeg"),
    ],
    ids=["invalid-bytes", "svg", "over-5mb"],
)
def test_reject_bad_format_size_and_content(
    as_recorder: TestClient, content: bytes, mime: str
) -> None:
    dish = as_recorder.get("/api/v1/dishes").json()["items"][0]
    response = as_recorder.put(
        f"/api/v1/dishes/{dish['id']}/image", files={"file": ("file", content, mime)}
    )
    assert response.status_code == 422
    assert as_recorder.get(f"/api/v1/dishes/{dish['id']}").json()["image_url"] is None


def test_image_routes_require_login_and_write_role(
    client: TestClient, as_school_admin: TestClient
) -> None:
    dish = as_school_admin.get("/api/v1/dishes").json()["items"][0]
    path = f"/api/v1/dishes/{dish['id']}/image"
    assert (
        as_school_admin.put(path, files={"file": ("test.png", picture(), "image/png")}).status_code
        == 403
    )
    assert as_school_admin.delete(path).status_code == 403
    client.cookies.clear()
    assert client.get(path).status_code == 401
    assert client.put(path, files={"file": ("test.png", picture(), "image/png")}).status_code == 401


def test_missing_dish_is_not_created_by_upload(as_recorder: TestClient) -> None:
    assert (
        as_recorder.put(
            f"/api/v1/dishes/{uuid4()}/image", files={"file": ("test.png", picture(), "image/png")}
        ).status_code
        == 404
    )

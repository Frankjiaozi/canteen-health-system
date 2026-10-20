"""用户菜品图片：限量解码、去除元信息、统一 WebP、原子替换。"""

from __future__ import annotations

import os
import warnings
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import UUID

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import get_settings
from app.core.errors import BusinessRuleError

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}


def image_path(dish_id: UUID) -> Path:
    return get_settings().dish_image_dir / f"{dish_id}.webp"


def image_url(dish_id: UUID) -> str | None:
    path = image_path(dish_id)
    try:
        version = path.stat().st_mtime_ns
    except FileNotFoundError:
        return None
    return f"{get_settings().api_prefix}/dishes/{dish_id}/image?v={version}"


def save_image(dish_id: UUID, content: bytes, content_type: str | None) -> None:
    if not content or len(content) > MAX_IMAGE_BYTES:
        raise BusinessRuleError("请选择不超过 5MB 的图片")
    if content_type not in ALLOWED_TYPES:
        raise BusinessRuleError("仅支持 JPG、PNG、WebP 图片")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as source:
                if source.format not in {"JPEG", "PNG", "WEBP"}:
                    raise BusinessRuleError("仅支持 JPG、PNG、WebP 图片")
                if source.width * source.height > MAX_IMAGE_PIXELS:
                    raise BusinessRuleError("图片像素过大，请压缩后上传")
                source.load()
                picture = ImageOps.exif_transpose(source).convert("RGB")
                picture.thumbnail((1600, 1600))
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise BusinessRuleError("图片无法读取，请选择完整有效的图片") from exc
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise BusinessRuleError("图片像素过大，请压缩后上传") from exc

    target = image_path(dish_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(dir=target.parent, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            picture.save(stream, format="WEBP", quality=88, exif=b"")
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

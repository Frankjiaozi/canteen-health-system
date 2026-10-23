"""确认每道初始化菜品有可读取、可发布的默认图片。"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
from app.db.seed import _DISHES  # noqa: E402


def main() -> int:
    directory = ROOT / "apps" / "web" / "public" / "design" / "dishes"
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    entries = manifest["images"]
    seed_names = {dish.name for dish in _DISHES}
    names = [entry["name"] for entry in entries]
    files = [entry["file"] for entry in entries]
    assert len(seed_names) == len(_DISHES) == 40, "初始化菜品数量发生变化"
    assert len(names) == len(set(names)) and set(names) == seed_names, "配图清单与菜品不一致"
    assert len(files) == len(set(files)), "配图文件不能复用同一文件名"

    module = (ROOT / "apps" / "web" / "src" / "features" / "dish" / "lib" / "defaultImage.ts").read_text(encoding="utf-8")
    mapping = dict(re.findall(r"^\s*([^:\n]+): '([^']+\.webp)',$", module, re.MULTILINE))
    assert set(mapping) == seed_names, "前端菜名映射未覆盖全部初始化菜品"
    for entry in entries:
        name, filename = entry["name"], entry["file"]
        assert mapping[name] == filename, f"{name} 的前端文件名不一致"
        path = directory / filename
        assert path.is_file() and path.stat().st_size > 5_000, f"{name} 的文件缺失或过小"
        with Image.open(path) as picture:
            assert picture.format == "WEBP" and picture.width > picture.height >= 700, name
            picture.verify()
    print(f"菜品配图检查通过：{len(entries)} 道菜，{sum((directory / filename).stat().st_size for filename in files):,} 字节")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

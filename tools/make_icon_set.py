#!/usr/bin/env python3
"""Finish asset catalog JSON + app icon renditions."""
import json, pathlib
from PIL import Image

ROOT = pathlib.Path("/mnt/c/Users/M/Desktop/zhiwei-tray/ios/ZhiweiTray/Resources")
ASSETS = ROOT / "Assets.xcassets"
ICONSET = ASSETS / "AppIcon.appiconset"
ICONSET.mkdir(parents=True, exist_ok=True)

(ASSETS / "Contents.json").write_text(json.dumps({"info": {"author": "xcode", "version": 1}}, indent=2), encoding="utf-8")

accent = {
    "colors": [{
        "color": {"color-space": "srgb", "components": {"alpha": "1.000", "blue": "0x4A", "green": "0x57", "red": "0x24"}},
        "idiom": "universal",
    }],
    "info": {"author": "xcode", "version": 1},
}
(ASSETS / "AccentColor.colorset").mkdir(exist_ok=True)
(ASSETS / "AccentColor.colorset" / "Contents.json").write_text(json.dumps(accent, indent=2), encoding="utf-8")

sizes = [
    ("iphone", "20x20", 2, 40), ("iphone", "20x20", 3, 60),
    ("iphone", "29x29", 2, 58), ("iphone", "29x29", 3, 87),
    ("iphone", "40x40", 2, 80), ("iphone", "40x40", 3, 120),
    ("iphone", "60x60", 2, 120), ("iphone", "60x60", 3, 180),
    ("ipad", "20x20", 1, 20), ("ipad", "20x20", 2, 40),
    ("ipad", "29x29", 1, 29), ("ipad", "29x29", 2, 58),
    ("ipad", "40x40", 1, 40), ("ipad", "40x40", 2, 80),
    ("ipad", "76x76", 1, 76), ("ipad", "76x76", 2, 152),
    ("ipad", "83.5x83.5", 2, 167),
    ("ios-marketing", "1024x1024", 1, 1024),
]
base = Image.open(ICONSET / "icon-1024.png").convert("RGB")
images = []
for idiom, size, scale, px in sizes:
    name = f"icon-{px}.png"
    if px != 1024:
        base.resize((px, px), Image.LANCZOS).save(ICONSET / name, "PNG")
    images.append({
        "filename": name,
        "idiom": idiom,
        "scale": f"{scale}x",
        "size": size,
    })
(ICONSET / "Contents.json").write_text(json.dumps({"images": images, "info": {"author": "xcode", "version": 1}}, indent=2), encoding="utf-8")
print("assets ok", len(images))

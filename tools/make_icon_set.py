#!/usr/bin/env python3
"""Regenerate the app icon as a full-bleed seal."""
import pathlib
from PIL import Image, ImageDraw, ImageFont

ICONSET = pathlib.Path("/mnt/c/Users/M/Desktop/zhiwei-tray/ios/ZhiweiTray/Resources/Assets.xcassets/AppIcon.appiconset")
GREEN = "#24574A"
CREAM = "#F7F3EC"
ORANGE = "#E4693B"

icon = Image.new("RGB", (1024, 1024), GREEN)
d = ImageDraw.Draw(icon)
d.ellipse([176, 176, 848, 848], fill=CREAM)
d.ellipse([214, 214, 810, 810], outline=ORANGE, width=34)
font = ImageFont.truetype("/mnt/c/Windows/Fonts/msyhbd.ttc", 352)
text = "味"
box = d.textbbox((0, 0), text, font=font)
w = box[2] - box[0]
h = box[3] - box[1]
d.text(((1024 - w) / 2 - box[0], (1024 - h) / 2 - box[1] - 6), text, font=font, fill=GREEN)
icon.save(ICONSET / "icon-1024.png")

sizes = [40, 60, 58, 87, 80, 120, 120, 180, 20, 40, 29, 58, 40, 80, 76, 152, 167]
for px in sizes:
    icon.resize((px, px), Image.LANCZOS).save(ICONSET / f"icon-{px}.png", "PNG")
print("icons regenerated")

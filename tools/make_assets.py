#!/usr/bin/env python3
"""Generate the Zhiwei Tray demo dataset, dish photos, and app icon."""
import json, pathlib, shutil
from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_IMG = pathlib.Path("/mnt/c/Users/M/Desktop/canteen_project/apps/web/dist/design/dishes")
CORE = ROOT / "ios/TrayCore/Sources/TrayCore/Resources"
APP = ROOT / "ios/ZhiweiTray/Resources"
DISHES = APP / "Dishes"
ICONSET = APP / "Assets.xcassets/AppIcon.appiconset"
for p in (CORE, DISHES, ICONSET):
    p.mkdir(parents=True, exist_ok=True)

# name, file, category, price, kcal, protein, fat, carbs, fiber, sodium, allergens, tags, ingredients, vegetarian, spicy, popularity, note
D = [
    ("番茄炒蛋", "tomato-eggs", "protein", 6.0, 168, 8.5, 12.0, 6.0, 1.2, 480, ["鸡蛋"], ["下饭", "招牌"], ["番茄", "鸡蛋", "食用油", "盐"], False, 0, 96, "番茄酸甜，鸡蛋滑嫩，食堂常青款。"),
    ("清炒西兰花", "stir_broccoli", "vegetable", 5.0, 70, 4.5, 4.0, 5.0, 3.2, 320, [], ["低脂", "高纤维"], ["西兰花", "蒜", "食用油", "盐"], True, 0, 78, "大火快炒，保留脆嫩口感。"),
    ("土豆炖牛肉", "potato-beef", "protein", 12.0, 260, 16.0, 12.0, 16.0, 2.0, 620, [], ["高蛋白", "下饭"], ["牛肉", "土豆", "胡萝卜", "酱油"], False, 0, 91, "牛肉炖至软烂，土豆吸满汤汁。"),
    ("紫菜蛋花汤", "nori_egg_soup", "soup", 2.0, 45, 3.5, 2.0, 2.0, 0.4, 500, ["鸡蛋"], ["清淡"], ["紫菜", "鸡蛋", "香油", "盐"], False, 0, 84, "清口解腻，配饭刚好。"),
    ("米饭", "steamed_rice", "staple", 1.0, 232, 5.2, 0.6, 51.6, 0.6, 2, [], ["主食"], ["大米"], True, 0, 99, "东北大米，现蒸现卖。"),
    ("馒头", "steamed_bun", "staple", 1.0, 223, 7.0, 1.1, 47.0, 1.3, 165, ["小麦"], ["主食"], ["小麦粉", "酵母"], True, 0, 82, "老面发酵，麦香扎实。"),
    ("番茄蛋汤", "tomato-egg-soup", "soup", 2.0, 50, 3.0, 2.5, 3.0, 0.5, 480, ["鸡蛋"], ["清淡"], ["番茄", "鸡蛋", "葱花"], False, 0, 80, "番茄熬出沙，酸香开胃。"),
    ("冬瓜排骨汤", "winter-melon-ribs", "soup", 6.0, 110, 8.0, 7.0, 3.0, 0.5, 520, [], ["清淡"], ["冬瓜", "排骨", "姜片"], False, 0, 86, "慢炖两小时，汤色清亮。"),
    ("红烧肉", "braised-pork", "protein", 12.0, 380, 12.0, 34.0, 6.0, 0.2, 640, [], ["高脂", "下饭"], ["五花肉", "冰糖", "酱油", "八角"], False, 0, 88, "肥瘦相间，浓油赤酱。"),
    ("鸡腿烧土豆", "chicken-potatoes", "protein", 11.0, 300, 20.0, 15.0, 19.0, 1.8, 700, [], ["高蛋白", "下饭"], ["鸡腿", "土豆", "酱油", "姜"], False, 0, 90, "带骨鸡腿，肉汁拌饭一绝。"),
    ("清蒸鲈鱼", "steamed-bass", "protein", 15.0, 180, 28.0, 6.0, 1.0, 0.0, 420, ["鱼类"], ["高蛋白", "低脂", "清淡"], ["鲈鱼", "姜丝", "葱丝", "蒸鱼豉油"], False, 0, 85, "当日鲜鱼，清蒸锁鲜。"),
    ("宫保鸡丁", "kung-pao-chicken", "protein", 10.0, 280, 18.0, 18.0, 12.0, 1.0, 720, ["花生", "大豆"], ["微辣", "下饭"], ["鸡胸肉", "花生", "干辣椒", "黄瓜"], False, 1, 89, "糊辣荔枝口，花生酥脆。"),
    ("木耳炒肉片", "wood-ear-pork", "protein", 9.0, 210, 14.0, 14.0, 6.0, 1.6, 560, [], ["下饭"], ["猪里脊", "木耳", "青椒"], False, 0, 76, "木耳爽脆，肉片嫩滑。"),
    ("麻婆豆腐", "mapo-tofu", "protein", 7.0, 220, 12.0, 15.0, 8.0, 1.2, 760, ["大豆"], ["微辣", "下饭"], ["嫩豆腐", "肉末", "豆瓣酱", "花椒"], False, 1, 87, "麻辣鲜香，豆腐嫩而不碎。"),
    ("青椒炒肉丝", "pepper-pork", "protein", 9.0, 200, 13.0, 13.0, 6.0, 1.4, 540, [], ["下饭"], ["青椒", "猪里脊", "蒜"], False, 0, 79, "青椒清香，肉丝滑嫩。"),
    ("胡萝卜炒鸡蛋", "carrot-eggs", "protein", 6.0, 170, 8.0, 12.0, 7.0, 2.0, 460, ["鸡蛋"], ["下饭"], ["胡萝卜", "鸡蛋", "葱花"], False, 0, 74, "颜色明亮，甜咸适口。"),
    ("蒜蓉油菜", "garlic_bok_choy", "vegetable", 4.0, 65, 3.0, 4.0, 4.0, 2.5, 300, [], ["低脂", "高纤维"], ["小油菜", "蒜蓉"], True, 0, 83, "蒜香浓郁，青菜碧绿。"),
    ("醋溜白菜", "vinegar_cabbage", "vegetable", 4.0, 80, 2.0, 5.0, 7.0, 2.0, 430, [], ["酸香", "低脂"], ["白菜", "醋", "干辣椒"], True, 0, 77, "锅气足，酸香解腻。"),
    ("凉拌黄瓜", "cucumber_salad", "vegetable", 4.0, 45, 1.5, 2.0, 5.0, 1.5, 380, [], ["清爽", "低脂"], ["黄瓜", "蒜", "香醋", "香油"], True, 0, 81, "现拍现拌，脆爽开胃。"),
    ("干煸豆角", "dry_fried_beans", "vegetable", 6.0, 150, 4.0, 10.0, 11.0, 3.0, 480, [], ["微辣", "下饭"], ["豆角", "干辣椒", "蒜"], True, 1, 78, "豆角起皱，干香微辣。"),
    ("冬瓜蛋花汤", "winter_melon_egg_soup", "soup", 2.0, 40, 2.5, 2.0, 2.0, 0.3, 460, ["鸡蛋"], ["清淡"], ["冬瓜", "鸡蛋", "葱花"], False, 0, 75, "清淡利口，夏日常备。"),
    ("番茄豆腐汤", "tomato_tofu_soup", "soup", 3.0, 55, 4.0, 2.5, 4.0, 0.6, 480, ["大豆"], ["清淡"], ["番茄", "嫩豆腐", "葱花"], True, 0, 73, "番茄微酸，豆腐滑嫩。"),
    ("紫菜豆腐汤", "nori_tofu_soup", "soup", 3.0, 50, 4.5, 2.0, 3.0, 0.5, 500, ["大豆"], ["清淡"], ["紫菜", "嫩豆腐", "虾皮"], False, 0, 72, "海味清鲜，暖胃。"),
    ("蒜蓉西兰花", "garlic_broccoli", "vegetable", 5.0, 75, 4.0, 4.5, 5.0, 3.0, 330, [], ["低脂", "高纤维"], ["西兰花", "蒜蓉"], True, 0, 80, "蒜蓉提香，少油快炒。"),
    ("青椒土豆丝", "pepper_potato", "vegetable", 4.0, 140, 3.0, 7.0, 17.0, 2.0, 420, [], ["下饭"], ["土豆", "青椒", "醋"], True, 0, 86, "切丝均匀，爽脆带酸。"),
    ("洋葱木耳", "onion_wood_ear", "vegetable", 5.0, 90, 3.0, 5.0, 8.0, 2.5, 390, [], ["低脂", "高纤维"], ["洋葱", "木耳", "青椒"], True, 0, 70, "洋葱微甜，木耳脆弹。"),
    ("清炒胡萝卜", "carrot_stir", "vegetable", 4.0, 85, 2.0, 5.5, 8.0, 2.8, 340, [], ["低脂"], ["胡萝卜", "蒜", "食用油"], True, 0, 69, "胡萝卜素丰富，清甜。"),
    ("番茄炖牛肉", "tomato_beef", "protein", 13.0, 240, 18.0, 11.0, 12.0, 2.0, 580, [], ["高蛋白", "下饭"], ["牛肉", "番茄", "洋葱"], False, 0, 88, "番茄炖化，牛肉入味。"),
    ("鸡丁炒黄瓜", "chicken_cucumber", "protein", 9.0, 190, 16.0, 10.0, 6.0, 1.2, 520, [], ["高蛋白", "低脂"], ["鸡胸肉", "黄瓜", "胡萝卜"], False, 0, 75, "清爽不腻，健身党常点。"),
    ("虾仁豆腐", "prawn_tofu", "protein", 12.0, 160, 15.0, 7.0, 6.0, 0.8, 560, ["虾", "大豆"], ["高蛋白", "低脂"], ["虾仁", "嫩豆腐", "青豆"], False, 0, 84, "虾仁弹牙，豆腐吸汁。"),
    ("白粥", "congee", "staple", 1.0, 90, 2.0, 0.3, 20.0, 0.3, 5, [], ["清淡"], ["大米", "水"], True, 0, 88, "熬到米花开，暖胃。"),
    ("花卷", "steamed_roll", "staple", 1.0, 214, 6.0, 1.0, 45.0, 1.1, 150, ["小麦"], ["主食"], ["小麦粉", "葱花", "酵母"], True, 0, 79, "层层葱香，松软。"),
    ("煮鸡蛋", "boiled_egg", "protein", 1.5, 72, 6.5, 5.0, 0.5, 0.0, 65, ["鸡蛋"], ["高蛋白"], ["鸡蛋"], False, 0, 90, "每天现煮，剥壳即食。"),
    ("鸡蛋饼", "egg_pancake", "staple", 4.0, 260, 9.0, 12.0, 29.0, 1.0, 380, ["鸡蛋", "小麦"], ["招牌"], ["面粉", "鸡蛋", "葱花"], False, 0, 87, "现摊现卖，边缘焦脆。"),
    ("热牛奶", "hot_milk", "protein", 3.0, 160, 8.0, 9.0, 12.0, 0.0, 110, ["牛奶"], ["高蛋白"], ["牛奶"], False, 0, 85, "温热适口，早餐搭档。"),
    ("晨光番茄蛋", "breakfast_tomato_egg", "protein", 5.0, 150, 7.0, 10.0, 6.0, 1.0, 420, ["鸡蛋"], ["下饭"], ["番茄", "鸡蛋", "葱花"], False, 0, 72, "早餐限定的番茄炒蛋。"),
    ("清炒小油菜", "breakfast_bok_choy", "vegetable", 4.0, 60, 3.0, 3.5, 4.0, 2.2, 300, [], ["低脂", "高纤维"], ["小油菜", "蒜"], True, 0, 71, "清晨第一口绿叶菜。"),
    ("豆腐蛋花汤", "breakfast_tofu_soup", "soup", 3.0, 60, 5.0, 3.0, 3.0, 0.5, 490, ["鸡蛋", "大豆"], ["清淡"], ["嫩豆腐", "鸡蛋", "紫菜"], False, 0, 68, "清淡暖胃，配饼刚好。"),
    ("胡萝卜鸡蛋饼", "breakfast_carrot_pancake", "staple", 4.0, 240, 8.0, 11.0, 28.0, 1.5, 400, ["鸡蛋", "小麦"], ["招牌"], ["面粉", "鸡蛋", "胡萝卜"], False, 0, 76, "胡萝卜丝藏在饼里，甜香。"),
    ("醋香白菜", "breakfast_cabbage", "vegetable", 4.0, 75, 2.0, 4.5, 7.0, 2.0, 410, [], ["酸香"], ["白菜", "醋", "蒜"], True, 0, 66, "酸香开胃，早餐解腻。"),
]

dishes = {}
for (name, key, cat, price, kcal, p, f, c, fib, na, allergens, tags, ing, veg, spicy, pop, note) in D:
    dishes[key] = {
        "id": key, "name": name, "category": cat, "price": price,
        "stall": "一食堂 · 家常菜" if cat != "staple" or key in ("steamed_rice",) else "二食堂 · 面点",
        "image": key,
        "nutrition": {"calories": kcal, "protein": p, "fat": f, "carbs": c, "fiber": fib, "sodium": na},
        "allergens": allergens, "tags": tags, "ingredients": ing,
        "vegetarian": veg, "spicy": spicy, "popularity": pop, "note": note,
    }

# Breakfast items also available at breakfast; lunch/dinner pools.
breakfast_ids = ["congee", "steamed_roll", "steamed_bun", "boiled_egg", "egg_pancake", "hot_milk",
                 "breakfast_tomato_egg", "breakfast_bok_choy", "breakfast_tofu_soup",
                 "breakfast_carrot_pancake", "breakfast_cabbage"]
lunch_staples = ["steamed_rice", "steamed_bun"]
lunch_proteins = ["potato-beef", "braised-pork", "chicken-potatoes", "steamed-bass", "kung-pao-chicken",
                  "wood-ear-pork", "mapo-tofu", "pepper-pork", "carrot-eggs", "tomato_beef",
                  "chicken_cucumber", "prawn_tofu", "tomato-eggs"]
lunch_veg = ["stir_broccoli", "garlic_bok_choy", "vinegar_cabbage", "cucumber_salad", "dry_fried_beans",
             "garlic_broccoli", "pepper_potato", "onion_wood_ear", "carrot_stir"]
lunch_soups = ["nori_egg_soup", "tomato-egg-soup", "winter-melon-ribs", "winter_melon_egg_soup",
               "tomato_tofu_soup", "nori_tofu_soup"]

def rot(pool, i, n):
    return [pool[(i * 3 + j) % len(pool)] for j in range(n)]

week = []
for day in range(7):
    b = [rot(breakfast_ids[:3], day, 1)[0], rot(breakfast_ids[3:7], day, 1)[0],
         rot(breakfast_ids[7:], day, 2)[0], rot(breakfast_ids[7:], day, 2)[1]]
    lunch = {
        "type": "lunch", "time": "11:30 – 13:00",
        "dishIDs": rot(lunch_staples, day, 2) + rot(lunch_proteins, day, 3) + rot(lunch_veg, day, 3) + rot(lunch_soups, day, 2),
    }
    dinner = {
        "type": "dinner", "time": "17:30 – 19:00",
        "dishIDs": rot(lunch_staples, day + 1, 2) + rot(lunch_proteins, day + 4, 3) + rot(lunch_veg, day + 2, 3) + rot(lunch_soups, day + 3, 2),
    }
    bre = {"type": "breakfast", "time": "07:00 – 09:00", "dishIDs": b}
    week.append({"weekday": day + 1, "label": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][day],
                 "meals": [bre, lunch, dinner]})

payload = {
    "canteen": {"name": "知味 · 第一食堂", "school": "示例大学", "updated": "每日 06:30 同步"},
    "dishes": dishes,
    "week": week,
    "meta": {
        "note": "演示数据：菜品营养值按标准份量估算，用于产品体验，正式版由食堂配方核算后下发。",
        "oilPerPerson": 28, "saltPerPerson": 4.2, "traceBatches": 12,
    },
}
(CORE / "menu.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print("dishes", len(dishes), "json", (CORE / "menu.json").stat().st_size)

# Convert images: 900px wide JPEG.
for key in dishes:
    src = SRC_IMG / f"{key}.webp"
    if not src.exists():
        print("MISSING", src)
        continue
    im = Image.open(src).convert("RGB")
    im.thumbnail((900, 900), Image.LANCZOS)
    im.save(DISHES / f"{key}.jpg", "JPEG", quality=82, optimize=True)
print("images", len(list(DISHES.glob('*.jpg'))))

# App icon.
ICON = Image.new("RGB", (1024, 1024), "#F5EFE3")
d = ImageDraw.Draw(ICON)
d.rounded_rectangle([72, 72, 952, 952], radius=220, fill="#24574A")
d.ellipse([222, 300, 802, 800], fill="#F5EFE3")
d.ellipse([262, 340, 762, 760], fill="#E4693B")
d.ellipse([300, 378, 724, 722], fill="#F5EFE3")
font = ImageFont.truetype("/mnt/c/Windows/Fonts/msyhbd.ttc", 360)
text = "味"
box = d.textbbox((0, 0), text, font=font)
d.text(((1024 - (box[2] - box[0])) / 2 - box[0], (1024 - (box[3] - box[1])) / 2 - box[1] - 20), text, font=font, fill="#24574A")
d.rectangle([430, 690, 594, 712], fill="#E4693B")
ICON.save(ICONSET / "icon-1024.png")
print("icon ok")

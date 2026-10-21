"""从「食物营养成分查询平台」拉取权威营养值，生成可追溯的参照快照。

数据来源：中国疾病预防控制中心营养与健康所 —— 食物营养成分查询平台
          https://nlc.chinanutri.cn/fq/foodlist_0_0_0_0_0_1.htm

## 这个脚本解决什么问题

系统要求任何营养数据都能点开看到来源与版本，而种子数据原先标注的是
「人工录入参考值，待核对」。这个脚本就是把「待核对」真正做完的工具：按映射表
去平台取数，把**条目 ID、平台条目名、原始 kJ、换算后的五项营养、食部、
查询日期**一并落盘成快照提交进仓库。

**运行期不联网，不依赖那个网站。** 快照才是数据源，平台只是取数时用一次。
第三方站点改版、限流、下线都不会影响系统。

## 用法

    pnpm nutrition:list 大白菜   # 人工挑条目：列候选
    pnpm nutrition:fetch         # 取数并写快照
    pnpm nutrition:verify        # 重新取数，与已提交的快照逐条比对

映射表在 ``apps/api/tools/nutrition_sources.json``。

## 三个口径约定（写错任何一个整份数据就废了）

1. 平台全部是**每 100 克可食部**的数值，与 ``Ingredient`` / ``Seasoning`` 模型一致。
2. 平台**只给能量（kJ）**，没有千卡。按热化学卡 ``1 kcal = 4.184 kJ`` 换算并保留
   2 位小数落库，原始 kJ 值一并写下，任何人都能复算。
3. 平台用 ``Tr`` 表示未检出、``—`` 或留空表示未检测。``Tr`` 按 0 处理；留空分两种：
   复合食品留空是真未知（落库为 null），单一成分物质留空是因为本身不含该成分
   （落库为 0）。哪种按哪种处理逐条写在映射表的 ``zero_fill`` 里，脚本不猜。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

BUSINESS_TIMEZONE = ZoneInfo("Asia/Shanghai")

#: 工具在 apps/api/tools/ 下，仓库根目录要往上数四层
REPO_ROOT = Path(__file__).resolve().parents[3]
SOURCES_PATH = Path(__file__).with_name("nutrition_sources.json")
OUTPUT_PATH = REPO_ROOT / "apps" / "api" / "app" / "db" / "nutrition_reference.json"

BASE_URL = "https://nlc.chinanutri.cn/fq/"
LIST_REFERER = BASE_URL + "foodlist_0_0_0_0_0_1.htm"
QUERY_URL = BASE_URL + "FoodInfoQueryAction!queryFoodInfoList.do"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

#: 热化学卡定义值。平台只给 kJ，千卡由它换算而来。
ENERGY_KJ_PER_KCAL = Decimal("4.184")

#: 平台返回的是**位置数组**，不是对象。下标 = 页面表头序号 + 2
#: （前两位是条目 ID 与图片文件名，第三位才是食物名称）。
FIELD_INDEX = {
    "name": 2,
    "shibu": 5,  # 食部
    "energy_kj": 7,
    "protein_g": 8,
    "fat_g": 9,
    "carb_g": 12,
    "sodium_mg": 24,
}

#: 落库的小数位，与模型上的 Numeric(precision, scale) 对齐
SCALES = {
    "edible_ratio": Decimal("0.0001"),
    "energy_kcal": Decimal("0.01"),
    "protein_g": Decimal("0.001"),
    "fat_g": Decimal("0.001"),
    "carb_g": Decimal("0.001"),
    "sodium_mg": Decimal("0.01"),
}

NUTRIENT_FIELDS = ("protein_g", "fat_g", "carb_g", "sodium_mg")
NULL_TOKENS = {"", "—", "-", "－"}
ZERO_TOKENS = {"Tr", "tr", "TR"}

#: 定位条目时最多翻几页。平台一页 8 条，搜索是子串匹配，
#: 「猪肉」这类词要翻到第 2 页才见到「猪肉(瘦)」。
MAX_PAGES = 5


class FetchError(RuntimeError):
    """取数失败——条目找不到或响应不符合预期。"""


@dataclass(frozen=True)
class Entry:
    """平台上的一个食物条目。"""

    food_id: int
    values: dict[str, str]

    @property
    def name(self) -> str:
        return self.values["name"]

    def raw(self, field: str) -> str:
        return self.values.get(field, "")


def _request(url: str, data: bytes | None = None) -> bytes:
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "User-Agent": USER_AGENT,
            "Referer": LIST_REFERER,
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()
    except urllib.error.URLError as error:  # pragma: no cover - 网络故障
        raise FetchError(f"访问 {url} 失败：{error}") from error


def query(keyword: str, page: int = 1) -> list[Entry]:
    """按关键词查一页。平台对括号不友好，所以调用方只用简单词。"""

    payload = urllib.parse.urlencode(
        {
            "categoryOne": "0",
            "categoryTwo": "0",
            "foodName": keyword,
            "pageNum": page,
            "field": "0",
            "flag": "0",
        }
    ).encode()
    body = json.loads(_request(QUERY_URL, payload).decode("utf-8"))
    entries: list[Entry] = []
    for row in body.get("list") or []:
        entries.append(
            Entry(
                food_id=int(row[0]),
                values={
                    field: (row[index] if len(row) > index else "")
                    for field, index in FIELD_INDEX.items()
                },
            )
        )
    return entries


def find(keyword: str, food_id: int) -> Entry:
    """翻页找到指定条目；找不到直接报错，不静默退回别的条目。"""

    for page in range(1, MAX_PAGES + 1):
        entries = query(keyword, page)
        if not entries:
            break
        for entry in entries:
            if entry.food_id == food_id:
                return entry
        time.sleep(0.2)
    raise FetchError(f"关键词「{keyword}」的前 {MAX_PAGES} 页里没有条目 {food_id}")


def _parse_number(raw: str, *, unit: str = "") -> Decimal | None:
    """``"12.7g"`` / ``"1475kJ"`` / ``"87%"`` → Decimal；空与「—」返回 None。"""

    text = raw.strip()
    if text in NULL_TOKENS:
        return None
    if text in ZERO_TOKENS:
        return Decimal("0")
    digits = text[: -len(unit)] if unit and text.endswith(unit) else text
    try:
        return Decimal(digits)
    except InvalidOperation:
        return None


def _quantize(value: Decimal, scale: Decimal) -> Decimal:
    return value.quantize(scale)


def to_kcal(energy_kj: Decimal) -> Decimal:
    return _quantize(energy_kj / ENERGY_KJ_PER_KCAL, SCALES["energy_kcal"])


def build_record(entry: Entry, zero_fill: tuple[str, ...]) -> dict[str, Any]:
    """把平台条目转成快照里的一条记录。"""

    energy_kj = _parse_number(entry.raw("energy_kj"), unit="kJ")
    if energy_kj is None:
        raise FetchError(f"条目 {entry.food_id}「{entry.name}」没有能量值，无法使用")

    edible = _parse_number(entry.raw("shibu"), unit="%")
    if edible is None:
        raise FetchError(f"条目 {entry.food_id}「{entry.name}」没有食部，无法使用")

    record: dict[str, Any] = {
        "food_id": entry.food_id,
        "entry_name": entry.name,
        "energy_kj": str(energy_kj),
        "energy_kcal": str(to_kcal(energy_kj)),
        "edible_ratio": str(_quantize(edible / 100, SCALES["edible_ratio"])),
        "zero_filled": [],
    }

    units = {"protein_g": "g", "fat_g": "g", "carb_g": "g", "sodium_mg": "mg"}
    for field in NUTRIENT_FIELDS:
        value = _parse_number(entry.raw(field), unit=units[field])
        if value is None and field in zero_fill:
            # 单一成分物质：平台留空是因为它本身不含该成分，写 0 才是对的
            value = Decimal("0")
            record["zero_filled"].append(field)
        record[field] = str(_quantize(value, SCALES[field])) if value is not None else None

    return record


def load_sources() -> dict[str, Any]:
    return json.loads(SOURCES_PATH.read_text(encoding="utf-8"))


def collect(verbose: bool = True) -> dict[str, Any]:
    """按映射表逐条取数，返回完整快照。"""

    sources = load_sources()
    items: dict[str, Any] = {}
    total = len(sources["items"])
    for index, (key, spec) in enumerate(sources["items"].items(), start=1):
        if spec.get("food_id") is None:
            if verbose:
                print(f"[{index}/{total}] {key:<15} 平台无对应条目，跳过：{spec.get('note', '')}")
            continue
        entry = find(spec["keyword"], spec["food_id"])
        record = build_record(entry, tuple(spec.get("zero_fill", ())))
        if spec.get("note"):
            record["mapping_note"] = spec["note"]
        items[key] = record
        if verbose:
            print(
                f"[{index}/{total}] {key:<15} {record['food_id']:>5} {record['entry_name']:<24}"
                f" {record['energy_kj']:>5} kJ → {record['energy_kcal']:>7} kcal"
                f"  食部 {record['edible_ratio']}"
            )
        time.sleep(0.2)

    return {
        "source": {
            **sources["source"],
            "queried_at": datetime.now(BUSINESS_TIMEZONE).date().isoformat(),
        },
        "items": dict(sorted(items.items())),
    }


def write_snapshot(snapshot: dict[str, Any]) -> None:
    OUTPUT_PATH.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def cmd_list(keyword: str) -> int:
    """人工挑条目时用：打印候选，方便确认该选哪一条。"""

    for page in range(1, MAX_PAGES + 1):
        entries = query(keyword, page)
        if not entries:
            break
        for entry in entries:
            energy = _parse_number(entry.raw("energy_kj"), unit="kJ")
            kcal = to_kcal(energy) if energy is not None else "—"
            print(
                f"{entry.food_id:>5} {entry.name:<26} 食部 {entry.raw('shibu'):<6}"
                f" 能量 {entry.raw('energy_kj'):<9}({kcal} kcal)"
                f" 蛋白 {entry.raw('protein_g'):<8} 脂肪 {entry.raw('fat_g'):<8}"
                f" 碳水 {entry.raw('carb_g'):<8} 钠 {entry.raw('sodium_mg')}"
            )
        time.sleep(0.2)
    return 0


def cmd_fetch() -> int:
    snapshot = collect()
    write_snapshot(snapshot)
    total = len(load_sources()["items"])
    print(
        f"\n已写入 {OUTPUT_PATH.relative_to(REPO_ROOT).as_posix()}："
        f"{len(snapshot['items'])}/{total} 条来自平台"
    )

    blanks = {
        key: [field for field in NUTRIENT_FIELDS if record[field] is None]
        for key, record in snapshot["items"].items()
    }
    blanks = {key: fields for key, fields in blanks.items() if fields}
    if blanks:
        print("\n下列条目有成分按缺失（null）落库，计算时会记入 missing_nutrients：")
        for key, fields in blanks.items():
            print(f"  {key:<15} {snapshot['items'][key]['entry_name']:<24} {fields}")

    zeroed = {key: record["zero_filled"] for key, record in snapshot["items"].items()}
    zeroed = {key: fields for key, fields in zeroed.items() if fields}
    if zeroed:
        print("\n下列条目有成分按 0 落库（单一成分物质，平台留空）：")
        for key, fields in zeroed.items():
            print(f"  {key:<15} {fields}")
    return 0


def cmd_verify() -> int:
    """重新取数并与已提交的快照逐条比对：数据被静默改过就靠这条拦住。"""

    if not OUTPUT_PATH.exists():
        print(f"快照不存在：{OUTPUT_PATH}", file=sys.stderr)
        return 1
    committed = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    live = collect(verbose=False)

    problems: list[str] = []
    for key, record in committed["items"].items():
        fresh = live["items"].get(key)
        if fresh is None:
            problems.append(f"{key}: 映射表里已没有这个条目")
            continue
        for field, expected in record.items():
            actual = fresh.get(field)
            if actual != expected:
                problems.append(f"{key}.{field}: 快照 {expected!r} ≠ 平台 {actual!r}")
    for key in live["items"]:
        if key not in committed["items"]:
            problems.append(f"{key}: 映射表里有、快照里没有，需要重新 fetch")

    if problems:
        print(f"发现 {len(problems)} 处不一致：")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print(f"快照与平台逐条一致：{len(committed['items'])} 条")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="食物营养成分参照数据的取数与校验")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("fetch", help="按映射表取数并写快照")
    sub.add_parser("verify", help="重新取数并与快照比对")
    list_parser = sub.add_parser("list", help="列候选条目，人工挑条目时用")
    list_parser.add_argument("keyword")
    args = parser.parse_args(argv[1:])

    try:
        if args.command == "fetch":
            return cmd_fetch()
        if args.command == "verify":
            return cmd_verify()
        return cmd_list(args.keyword)
    except FetchError as error:
        print(f"取数失败：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

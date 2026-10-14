"""批量导入：解析 → 校验 → 报告 → 执行。

刻意做成两步。整理配方的是一份 Excel，里面出现拼错的类别名、引用不到的食材名
几乎是必然。如果上传即写库，一次失误就会在库里留下半张表。所以先给逐行报告，
确认干净了再执行；校验不通过时**一行都不会写**。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any

from openpyxl import load_workbook
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError
from app.core.logging import get_logger
from app.modules.audit import service as audit_service
from app.modules.dish import repository as dish_repository
from app.modules.dish import service as dish_service
from app.modules.dish.schemas import RecipeIngredientLine, RecipePayload, RecipeSeasoningLine
from app.modules.importer.schemas import ImportCounts, ImportIssue, ImportReport
from app.modules.importer.template import build_template
from app.modules.ingredient import repository as ingredient_repository
from app.modules.ingredient import service as ingredient_service
from app.modules.nutrition import service as nutrition_service
from app.modules.seasoning import repository as seasoning_repository
from app.modules.seasoning import service as seasoning_service
from app.shared.enums import (
    AuditAction,
    CookingMethod,
    DishCategory,
    IngredientCategory,
    SeasoningCategory,
    resolve_labelled,
)

logger = get_logger(__name__)

SHEET_INGREDIENT = "食材"
SHEET_SEASONING = "调味料"
SHEET_DISH = "菜品"
SHEET_RECIPE = "配方"
ALL_SHEETS = (SHEET_INGREDIENT, SHEET_SEASONING, SHEET_DISH, SHEET_RECIPE)

TYPE_INGREDIENT = {"食材", "INGREDIENT"}
TYPE_SEASONING = {"调味料", "SEASONING"}


class _Issues:
    """收集逐行问题，顺便挡掉后续重复报同一行的噪声。"""

    def __init__(self) -> None:
        self.items: list[ImportIssue] = []

    def error(
        self, sheet: str, row: int | None, message: str, field_name: str | None = None
    ) -> None:
        self.items.append(
            ImportIssue(severity="error", sheet=sheet, row=row, field=field_name, message=message)
        )

    def warn(
        self, sheet: str, row: int | None, message: str, field_name: str | None = None
    ) -> None:
        self.items.append(
            ImportIssue(severity="warning", sheet=sheet, row=row, field=field_name, message=message)
        )

    @property
    def has_error(self) -> bool:
        return any(item.severity == "error" for item in self.items)


@dataclass
class _Parsed:
    ingredients: list[dict[str, Any]] = field(default_factory=list)
    seasonings: list[dict[str, Any]] = field(default_factory=list)
    dishes: list[dict[str, Any]] = field(default_factory=list)
    recipes: dict[str, list[tuple[str, str, Decimal, Decimal | None]]] = field(default_factory=dict)
    existing_dish_names: set[str] = field(default_factory=set)


def run_import(
    session: Session,
    content: bytes,
    *,
    actor_id: Any = None,
    actor_name: str | None = None,
    dry_run: bool,
    file_name: str | None = None,
) -> ImportReport:
    issues = _Issues()
    parsed = _parse(session, content, issues)

    if parsed is None:
        return ImportReport(dry_run=dry_run, ok=False, counts=[], issues=issues.items)

    counts = _counts(session, parsed)
    if issues.has_error or dry_run:
        return ImportReport(
            dry_run=dry_run, ok=not issues.has_error, counts=counts, issues=issues.items
        )

    recomputed = _apply(
        session, parsed, actor_id=actor_id, actor_name=actor_name, file_name=file_name
    )
    return ImportReport(
        dry_run=False,
        ok=True,
        counts=counts,
        issues=issues.items,
        recomputed_rows=recomputed,
    )


# ---------------------------------------------------------------------------
# 解析
# ---------------------------------------------------------------------------
def _parse(session: Session, content: bytes, issues: _Issues) -> _Parsed | None:
    try:
        workbook = load_workbook(BytesIO(content), data_only=True)
    except Exception as exc:
        issues.error("文件", None, f"无法读取这个文件，请确认是 .xlsx 格式（{exc}）")
        return None

    missing = [sheet for sheet in ALL_SHEETS if sheet not in workbook.sheetnames]
    if missing:
        issues.error("文件", None, f"缺少 sheet：{'、'.join(missing)}。请使用下载的模板")
        return None

    parsed = _Parsed()
    parsed.ingredients = _parse_ingredients(workbook[SHEET_INGREDIENT], issues)
    parsed.seasonings = _parse_seasonings(workbook[SHEET_SEASONING], issues)
    parsed.dishes = _parse_dishes(workbook[SHEET_DISH], issues, parsed.existing_dish_names)
    _parse_recipe(workbook[SHEET_RECIPE], issues, parsed)
    _cross_check(session, parsed, issues)
    return parsed


def _parse_ingredients(sheet: Any, issues: _Issues) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
        if _blank_row(raw):
            continue
        name = _text(_cell(raw, 0))
        if not name:
            issues.error(SHEET_INGREDIENT, index, "名称为空")
            continue
        if name in seen:
            issues.error(SHEET_INGREDIENT, index, f"名称「{name}」在表里重复")
            continue
        seen.add(name)

        category = resolve_labelled(IngredientCategory, _text(_cell(raw, 1)))
        if category is None:
            issues.error(SHEET_INGREDIENT, index, f"类别「{_text(_cell(raw, 1))}」无法识别", "类别")
            continue

        number_errors = False
        values: dict[str, Decimal | None] = {}
        for offset, field_name in (
            (2, "energy_kcal"),
            (3, "protein_g"),
            (4, "fat_g"),
            (5, "carb_g"),
            (6, "sodium_mg"),
        ):
            try:
                values[field_name] = _decimal(_cell(raw, offset), min_value=Decimal("0"))
            except ValueError as exc:
                issues.error(SHEET_INGREDIENT, index, str(exc), field_name)
                number_errors = True
        try:
            ratio = _decimal(_cell(raw, 7), min_value=Decimal("0"), max_value=Decimal("1"))
        except ValueError as exc:
            issues.error(SHEET_INGREDIENT, index, str(exc), "可食部比例(0-1)")
            number_errors = True
            ratio = None
        try:
            price = _decimal(_cell(raw, 8), min_value=Decimal("0"))
        except ValueError as exc:
            issues.error(SHEET_INGREDIENT, index, str(exc), "单价(元/千克)")
            number_errors = True
            price = None
        if number_errors:
            continue

        source = _text(_cell(raw, 9))
        if not source:
            issues.error(
                SHEET_INGREDIENT,
                index,
                "数据来源为空。营养数据必须能逐条追溯到出处，这一项不能省",
                "数据来源",
            )
            continue

        rows.append(
            {
                "name": name,
                "category": category,
                "energy_kcal": values["energy_kcal"],
                "protein_g": values["protein_g"],
                "fat_g": values["fat_g"],
                "carb_g": values["carb_g"],
                "sodium_mg": values["sodium_mg"],
                "edible_ratio": ratio if ratio is not None else Decimal("1.0"),
                "unit_price": price,
                "data_source": source,
                "source_version": _text(_cell(raw, 10)) or None,
                "note": _text(_cell(raw, 11)) or None,
                "is_active": True,
            }
        )
    return rows


def _parse_seasonings(sheet: Any, issues: _Issues) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
        if _blank_row(raw):
            continue
        name = _text(_cell(raw, 0))
        if not name:
            issues.error(SHEET_SEASONING, index, "名称为空")
            continue
        if name in seen:
            issues.error(SHEET_SEASONING, index, f"名称「{name}」在表里重复")
            continue
        seen.add(name)

        category = resolve_labelled(SeasoningCategory, _text(_cell(raw, 1)))
        if category is None:
            issues.error(SHEET_SEASONING, index, f"类别「{_text(_cell(raw, 1))}」无法识别", "类别")
            continue

        values: dict[str, Decimal | None] = {}
        failed = False
        for offset, field_name in (
            (3, "energy_kcal"),
            (4, "protein_g"),
            (5, "fat_g"),
            (6, "carb_g"),
            (7, "sodium_mg"),
        ):
            try:
                values[field_name] = _decimal(_cell(raw, offset), min_value=Decimal("0"))
            except ValueError as exc:
                issues.error(SHEET_SEASONING, index, str(exc), field_name)
                failed = True
        try:
            price = _decimal(_cell(raw, 8), min_value=Decimal("0"))
        except ValueError as exc:
            issues.error(SHEET_SEASONING, index, str(exc), "单价(元/千克)")
            failed = True
            price = None
        if failed:
            continue

        rows.append(
            {
                "name": name,
                "category": category,
                "unit": _text(_cell(raw, 2)) or "g",
                "energy_kcal": values["energy_kcal"],
                "protein_g": values["protein_g"],
                "fat_g": values["fat_g"],
                "carb_g": values["carb_g"],
                "sodium_mg": values["sodium_mg"],
                "unit_price": price,
                "data_source": _text(_cell(raw, 9)) or None,
                "note": _text(_cell(raw, 10)) or None,
                "is_active": True,
            }
        )
    return rows


def _parse_dishes(sheet: Any, issues: _Issues, existing_names: set[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
        if _blank_row(raw):
            continue
        name = _text(_cell(raw, 0))
        if not name:
            issues.error(SHEET_DISH, index, "名称为空")
            continue
        if name in seen:
            issues.error(SHEET_DISH, index, f"名称「{name}」在表里重复")
            continue
        seen.add(name)
        existing_names.add(name)

        category = resolve_labelled(DishCategory, _text(_cell(raw, 1)))
        if category is None:
            issues.error(SHEET_DISH, index, f"类别「{_text(_cell(raw, 1))}」无法识别", "类别")
            continue
        method = resolve_labelled(CookingMethod, _text(_cell(raw, 2)))
        if method is None:
            issues.error(
                SHEET_DISH, index, f"烹饪方式「{_text(_cell(raw, 2))}」无法识别", "烹饪方式"
            )
            continue

        try:
            serving = _decimal(_cell(raw, 3), min_value=Decimal("0.01"))
            pots = _decimal(_cell(raw, 4), min_value=Decimal("0.01"))
        except ValueError as exc:
            issues.error(SHEET_DISH, index, str(exc))
            continue
        assert serving is not None and pots is not None

        rows.append(
            {
                "name": name,
                "category": category,
                "cooking_method": method,
                "standard_serving_g": serving,
                "servings_per_pot": pots,
                "allergens": [
                    item.strip()
                    for item in _text(_cell(raw, 5)).replace("、", ",").split(",")
                    if item.strip()
                ],
                "note": _text(_cell(raw, 6)) or None,
                "is_active": True,
            }
        )
    return rows


def _parse_recipe(sheet: Any, issues: _Issues, parsed: _Parsed) -> None:
    for index, raw in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
        if _blank_row(raw):
            continue
        dish_name = _text(_cell(raw, 0))
        line_type = _text(_cell(raw, 1))
        item_name = _text(_cell(raw, 2))

        if not dish_name or not line_type or not item_name:
            issues.error(SHEET_RECIPE, index, "菜品名称、行类型、名称都不能为空")
            continue
        if line_type not in TYPE_INGREDIENT | TYPE_SEASONING:
            issues.error(SHEET_RECIPE, index, f"行类型「{line_type}」只能是「食材」或「调味料」")
            continue
        try:
            quantity = _decimal(_cell(raw, 3), min_value=Decimal("0.001"))
        except ValueError as exc:
            issues.error(SHEET_RECIPE, index, str(exc), "单份用量(克)")
            continue
        try:
            ratio = _decimal(_cell(raw, 4), min_value=Decimal("0"), max_value=Decimal("1"))
        except ValueError as exc:
            issues.error(SHEET_RECIPE, index, str(exc), "可食部比例覆盖")
            continue
        assert quantity is not None

        parsed.recipes.setdefault(dish_name, []).append((line_type, item_name, quantity, ratio))


def _cross_check(session: Session, parsed: _Parsed, issues: _Issues) -> None:
    """跨 sheet 校验：配方里引用的菜品、食材、调味料都必须能找到。"""
    ingredient_names = {row["name"] for row in parsed.ingredients}
    seasoning_names = {row["name"] for row in parsed.seasonings}
    dish_names = parsed.existing_dish_names

    for dish_name, lines in parsed.recipes.items():
        if dish_name not in dish_names:
            issues.error(
                SHEET_RECIPE,
                None,
                f"配方引用了「{dish_name}」，但「菜品」sheet 里没有它。请先在菜品表里补上",
            )
            continue
        seen: set[tuple[str, str]] = set()
        for line_type, item_name, _quantity, _ratio in lines:
            key = (line_type, item_name)
            if key in seen:
                issues.error(SHEET_RECIPE, None, f"「{dish_name}」的配方里「{item_name}」重复出现")
            seen.add(key)

            if line_type in TYPE_INGREDIENT and item_name not in ingredient_names:
                issues.error(
                    SHEET_RECIPE,
                    None,
                    f"「{dish_name}」的配方引用了食材「{item_name}」，但「食材」sheet 里没有它",
                )
            if line_type in TYPE_SEASONING and item_name not in seasoning_names:
                issues.error(
                    SHEET_RECIPE,
                    None,
                    f"「{dish_name}」的配方引用了调味料「{item_name}」，但「调味料」sheet 里没有它",
                )

    recipe_dish_names = set(parsed.recipes)
    for row in parsed.dishes:
        if row["name"] not in recipe_dish_names:
            issues.warn(
                SHEET_DISH,
                None,
                f"菜品「{row['name']}」没有配方，导入后无法计算营养值",
            )
    # 库里已有配方、但表里这次没给配方的菜品不动它的配方（只更新基础信息）


def _counts(session: Session, parsed: _Parsed) -> list[ImportCounts]:
    """预览阶段就告诉使用者「会新增多少、更新多少」，避免确认时心里没数。"""
    return [
        _count(parsed.ingredients, ingredient_repository.names_in_use, session, SHEET_INGREDIENT),
        _count(parsed.seasonings, seasoning_repository.names_in_use, session, SHEET_SEASONING),
        _count(parsed.dishes, dish_repository.names_in_use, session, SHEET_DISH),
        ImportCounts(sheet=SHEET_RECIPE, created=len(parsed.recipes)),
    ]


def _count(rows: list[dict[str, Any]], lookup: Any, session: Session, sheet: str) -> ImportCounts:
    names = [row["name"] for row in rows]
    existing = lookup(session, names)
    created = len(names) - len(existing)
    return ImportCounts(sheet=sheet, created=created, updated=len(existing))


# ---------------------------------------------------------------------------
# 执行
# ---------------------------------------------------------------------------
def _apply(
    session: Session,
    parsed: _Parsed,
    *,
    actor_id: Any,
    actor_name: str | None,
    file_name: str | None,
) -> int:
    ingredient_counts = ingredient_service.upsert_many(session, parsed.ingredients)
    seasoning_service.upsert_many(session, parsed.seasonings)

    recipes = _build_recipes(session, parsed)
    dish_service.upsert_many_with_recipe(session, parsed.dishes, recipes)

    audit_service.record(
        session,
        entity_type="import",
        entity_id=file_name or "batch-import",
        action=AuditAction.CREATE,
        actor_id=actor_id,
        actor_name=actor_name,
        after={
            "file": file_name,
            "食材": ingredient_counts,
            "菜品数": len(parsed.dishes),
            "配方数": len(recipes),
        },
        note="Excel 批量导入",
    )
    session.commit()

    recomputed = 0
    for dish_name in recipes:
        dish = dish_repository.find_by_name(session, dish_name)
        if dish is None:
            continue
        recomputed += nutrition_service.recompute_dish_nutrition(session, dish.id).rows
    logger.info("批量导入完成：配方 %d 份，重算营养结果 %d 条", len(recipes), recomputed)
    return recomputed


def _build_recipes(session: Session, parsed: _Parsed) -> dict[str, RecipePayload]:
    ingredient_ids = ingredient_repository.ids_by_name(
        session, [row["name"] for row in parsed.ingredients]
    )
    seasoning_ids = seasoning_repository.ids_by_name(
        session, [row["name"] for row in parsed.seasonings]
    )

    recipes: dict[str, RecipePayload] = {}
    for dish_name, lines in parsed.recipes.items():
        ingredients = [
            RecipeIngredientLine(
                ingredient_id=ingredient_ids[item_name],
                quantity_per_serving_g=quantity,
                edible_ratio_override=ratio,
            )
            for line_type, item_name, quantity, ratio in lines
            if line_type in TYPE_INGREDIENT
        ]
        seasonings = [
            RecipeSeasoningLine(
                seasoning_id=seasoning_ids[item_name], quantity_per_serving_g=quantity
            )
            for line_type, item_name, quantity, _ratio in lines
            if line_type in TYPE_SEASONING
        ]
        if not ingredients:
            raise BusinessRuleError(f"菜品「{dish_name}」的配方里没有食材，无法计算营养")
        recipes[dish_name] = RecipePayload(ingredients=ingredients, seasonings=seasonings)
    return recipes


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------
def _cell(row: tuple[Any, ...], index: int) -> Any:
    return row[index] if index < len(row) else None


def _blank_row(row: tuple[Any, ...]) -> bool:
    return all(value is None or str(value).strip() == "" for value in row)


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _decimal(
    value: Any, *, min_value: Decimal | None = None, max_value: Decimal | None = None
) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"「{value}」不是有效数字") from exc
    if min_value is not None and parsed < min_value:
        raise ValueError(f"「{value}」小于允许的最小值 {min_value}")
    if max_value is not None and parsed > max_value:
        raise ValueError(f"「{value}」大于允许的最大值 {max_value}")
    return parsed


__all__ = ["build_template", "run_import"]

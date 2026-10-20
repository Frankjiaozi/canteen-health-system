"""菜品与配方业务规则。

配方是这个系统里最需要人工投入、也最不能出错的数据，因此这里的规则写得比较实：
配方整体替换、每次保存递增版本号、改动全部留痕，保存后立即重算这道菜的营养结果，
让「改了配方 → 大屏上的数字跟着变」这件事立刻发生。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.logging import get_logger
from app.modules.audit import service as audit_service
from app.modules.dish import repository
from app.modules.dish.images import image_url
from app.modules.dish.models import Dish
from app.modules.dish.repository import IngredientLineValues, SeasoningLineValues
from app.modules.dish.schemas import (
    DishCreate,
    DishDetail,
    DishPage,
    DishRead,
    DishUpdate,
    NutritionSummary,
    RecipeIngredientRead,
    RecipePayload,
    RecipeRead,
    RecipeSeasoningRead,
    RecipeUpdateResult,
)
from app.modules.nutrition import service as nutrition_service
from app.modules.nutrition.engine import NutrientVector
from app.modules.nutrition.models import DishNutrition
from app.shared.decimals import scale_field, snapshot
from app.shared.enums import AuditAction, DishCategory, NutritionValueType

logger = get_logger(__name__)

ENTITY_TYPE = "dish"


# ---------------------------------------------------------------------------
# 读取
# ---------------------------------------------------------------------------
def to_read(dish: Dish, nutrition: NutritionSummary | None = None) -> DishRead:
    return DishRead(
        id=dish.id,
        image_url=image_url(dish.id),
        name=dish.name,
        category=dish.category,
        category_label=dish.category.label,
        cooking_method=dish.cooking_method,
        cooking_method_label=dish.cooking_method.label,
        standard_serving_g=scale_field(dish.standard_serving_g, "standard_serving_g"),
        servings_per_pot=scale_field(dish.servings_per_pot, "servings_per_pot"),
        allergens=list(dish.allergens or []),
        is_breakfast_staple=dish.is_breakfast_staple,
        note=dish.note,
        recipe_version=dish.recipe_version,
        is_active=dish.is_active,
        nutrition=nutrition,
        created_at=dish.created_at,
        updated_at=dish.updated_at,
    )


def list_dishes(
    session: Session,
    *,
    keyword: str | None = None,
    category: DishCategory | None = None,
    include_inactive: bool = False,
    page: int = 1,
    page_size: int = 20,
) -> DishPage:
    rows, total = repository.list_page(
        session,
        keyword=keyword,
        category=category,
        include_inactive=include_inactive,
        page=page,
        page_size=page_size,
    )
    summaries = _summaries(session, rows)
    return DishPage(
        items=[to_read(row, summaries.get(row.id)) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


def get_dish(session: Session, dish_id: UUID) -> Dish:
    dish = repository.get(session, dish_id)
    if dish is None:
        raise NotFoundError("菜品不存在")
    return dish


def get_dish_detail(session: Session, dish_id: UUID) -> DishDetail:
    dish = get_dish(session, dish_id)
    base = to_read(dish, _summaries(session, [dish]).get(dish.id))
    return DishDetail(**base.model_dump(), recipe=_read_recipe(session, [dish.id])[dish.id])


def _summaries(session: Session, dishes: Sequence[Dish]) -> dict[UUID, NutritionSummary]:
    """批量装配列表里的单份营养摘要。

    优先读落库的快照——那才是可追溯的正式结果。菜品要是从没被排进过菜单，
    就没有快照可读，这时按当前配方现算一份预览：配方录完就能看到数值，
    不必等到第一次供应之后。两者都不成立（没有配方明细）时返回空，
    界面显示「无配方」，而不是一个看起来像 0 的假值。
    """
    if not dishes:
        return {}

    stored = repository.latest_per_serving_nutrition(session, [dish.id for dish in dishes])
    summaries = {dish_id: _stored_summary(row) for dish_id, row in stored.items()}

    missing = [dish.id for dish in dishes if dish.id not in stored]
    for dish_id, nutrients in nutrition_service.preview_per_serving(session, missing).items():
        summaries[dish_id] = _preview_summary(nutrients)
    return summaries


def _stored_summary(row: DishNutrition) -> NutritionSummary:
    return NutritionSummary(
        date=row.date,
        value_type=row.value_type.value,
        energy_kcal=str(row.energy_kcal),
        protein_g=str(row.protein_g),
        fat_g=str(row.fat_g),
        carb_g=str(row.carb_g),
        sodium_mg=str(row.sodium_mg),
    )


def _preview_summary(nutrients: NutrientVector) -> NutritionSummary:
    return NutritionSummary(
        date=None,
        value_type=NutritionValueType.THEORETICAL.value,
        energy_kcal=str(nutrients.energy_kcal),
        protein_g=str(nutrients.protein_g),
        fat_g=str(nutrients.fat_g),
        carb_g=str(nutrients.carb_g),
        sodium_mg=str(nutrients.sodium_mg),
    )


def _read_recipe(session: Session, dish_ids: Sequence[UUID]) -> dict[UUID, RecipeRead]:
    """批量装配配方明细。"""
    ingredient_lines: dict[UUID, list[RecipeIngredientRead]] = {dish_id: [] for dish_id in dish_ids}
    seasoning_lines: dict[UUID, list[RecipeSeasoningRead]] = {dish_id: [] for dish_id in dish_ids}

    ingredient_rows, seasoning_rows = repository.load_recipe_rows(session, list(dish_ids))
    for ingredient_item, ingredient in ingredient_rows:
        ingredient_lines[ingredient_item.dish_id].append(
            RecipeIngredientRead(
                ingredient_id=ingredient.id,
                ingredient_name=ingredient.name,
                ingredient_active=ingredient.is_active,
                quantity_per_serving_g=str(ingredient_item.quantity_per_serving_g),
                edible_ratio_override=snapshot(ingredient_item.edible_ratio_override),
                unit_price=snapshot(ingredient.unit_price),
                energy_kcal=snapshot(ingredient.energy_kcal),
                protein_g=snapshot(ingredient.protein_g),
                fat_g=snapshot(ingredient.fat_g),
                carb_g=snapshot(ingredient.carb_g),
                sodium_mg=snapshot(ingredient.sodium_mg),
                note=ingredient_item.note,
            )
        )
    for seasoning_item, seasoning in seasoning_rows:
        seasoning_lines[seasoning_item.dish_id].append(
            RecipeSeasoningRead(
                seasoning_id=seasoning.id,
                seasoning_name=seasoning.name,
                seasoning_active=seasoning.is_active,
                quantity_per_serving_g=str(seasoning_item.quantity_per_serving_g),
                unit_price=snapshot(seasoning.unit_price),
                note=seasoning_item.note,
            )
        )

    return {
        dish_id: RecipeRead(
            ingredients=sorted(
                ingredient_lines[dish_id], key=lambda line: -float(line.quantity_per_serving_g)
            ),
            seasonings=sorted(
                seasoning_lines[dish_id], key=lambda line: -float(line.quantity_per_serving_g)
            ),
        )
        for dish_id in dish_ids
    }


# ---------------------------------------------------------------------------
# 写入
# ---------------------------------------------------------------------------
def create_dish(
    session: Session,
    payload: DishCreate,
    *,
    actor_id: UUID | None = None,
    actor_name: str | None = None,
    audit_note: str | None = None,
) -> DishDetail:
    if repository.find_by_name(session, payload.name) is not None:
        raise ConflictError(f"菜品「{payload.name}」已存在")

    base = payload.model_dump(exclude={"recipe"})
    dish = Dish(**base)
    session.add(dish)
    session.flush()

    if payload.recipe is not None:
        _validate_recipe(session, payload.recipe)
        _write_recipe(session, dish, payload.recipe)

    audit_service.record(
        session,
        entity_type=ENTITY_TYPE,
        entity_id=dish.id,
        action=AuditAction.CREATE,
        actor_id=actor_id,
        actor_name=actor_name,
        after=_snapshot(dish),
        note="｜".join(
            part
            for part in (
                audit_note,
                "新建菜品" + ("（含配方）" if payload.recipe else "（暂无配方）"),
            )
            if part
        ),
    )
    session.commit()
    return get_dish_detail(session, dish.id)


def update_dish(
    session: Session,
    dish_id: UUID,
    payload: DishUpdate,
    *,
    actor_id: UUID | None = None,
    actor_name: str | None = None,
    audit_note: str | None = None,
) -> DishDetail:
    """修改菜品基础信息。`audit_note` 用来说明这条改动的来源（例如助手代改）。"""
    dish = get_dish(session, dish_id)
    changes = payload.model_dump(exclude_unset=True)

    new_name = changes.get("name")
    if new_name and new_name != dish.name:
        existing = repository.find_by_name(session, new_name)
        if existing is not None and existing.id != dish.id:
            raise ConflictError(f"菜品「{new_name}」已存在")

    before = _snapshot(dish)
    for field, value in changes.items():
        setattr(dish, field, value)
    session.flush()
    after = _snapshot(dish)

    if before != after:
        audit_service.record(
            session,
            entity_type=ENTITY_TYPE,
            entity_id=dish.id,
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            actor_name=actor_name,
            before=before,
            after=after,
            note="｜".join(part for part in (audit_note, "修改菜品基础信息") if part),
        )
    session.commit()
    return get_dish_detail(session, dish.id)


def replace_recipe(
    session: Session,
    dish_id: UUID,
    payload: RecipePayload,
    *,
    actor_id: UUID | None = None,
    actor_name: str | None = None,
    audit_note: str | None = None,
) -> RecipeUpdateResult:
    """保存配方：整体替换、版本递增、留痕，然后立刻重算营养。"""
    dish = get_dish(session, dish_id)
    _validate_recipe(session, payload)

    # 内容一模一样就没必要递增版本、留一条无意义的修改记录，
    # 也没有重算的必要。版本号要能代表「配方确实变过几次」。
    if _recipe_signature(session, dish_id) == _payload_signature(payload):
        return RecipeUpdateResult(
            dish=get_dish_detail(session, dish_id),
            recipe_version=dish.recipe_version,
            recomputed_rows=0,
        )

    before = _recipe_snapshot(session, dish_id)
    _write_recipe(session, dish, payload)
    dish.recipe_version += 1
    session.flush()
    after = _recipe_snapshot(session, dish_id)

    audit_service.record(
        session,
        entity_type=ENTITY_TYPE,
        entity_id=dish.id,
        action=AuditAction.UPDATE,
        actor_id=actor_id,
        actor_name=actor_name,
        before=before,
        after=after,
        note="｜".join(part for part in (audit_note, f"配方更新至 v{dish.recipe_version}") if part),
    )
    session.commit()

    report = nutrition_service.recompute_dish_nutrition(session, dish_id)
    logger.info(
        "配方已更新：%s → v%d，重算营养结果 %d 条",
        dish.name,
        dish.recipe_version,
        report.rows,
    )
    return RecipeUpdateResult(
        dish=get_dish_detail(session, dish_id),
        recipe_version=dish.recipe_version,
        recomputed_rows=report.rows,
    )


def count_recipes_using_ingredient(session: Session, ingredient_id: UUID) -> int:
    """这个食材被多少个配方引用。

    停用食材前要能说清影响面（「有 6 个配方在用它」），否则用户是在盲签；
    这个数也用在助手的方案预览上。
    """
    return repository.ingredient_usage_count(session, ingredient_id)


def dish_menu_usage(session: Session, dish_id: UUID) -> int:
    """这道菜被历史菜单引用过多少次（停用前的影响面提示）。"""
    return repository.dish_usage_count(session, dish_id)


def deactivate_dish(
    session: Session,
    dish_id: UUID,
    *,
    actor_id: UUID | None = None,
    actor_name: str | None = None,
    audit_note: str | None = None,
) -> DishDetail:
    """停用菜品。菜单里引用过它同样不物理删除——历史营养结果要能回溯。"""
    dish = get_dish(session, dish_id)
    if not dish.is_active:
        return get_dish_detail(session, dish_id)

    usage = repository.dish_usage_count(session, dish_id)
    dish.is_active = False
    session.flush()

    audit_service.record(
        session,
        entity_type=ENTITY_TYPE,
        entity_id=dish.id,
        action=AuditAction.DELETE,
        actor_id=actor_id,
        actor_name=actor_name,
        before=_snapshot(dish),
        note="｜".join(
            part
            for part in (audit_note, f"停用菜品（历史菜单中引用 {usage} 次，数据保留）")
            if part
        ),
    )
    session.commit()
    return get_dish_detail(session, dish_id)


def reactivate_dish(
    session: Session,
    dish_id: UUID,
    *,
    actor_id: UUID | None = None,
    actor_name: str | None = None,
    audit_note: str | None = None,
) -> DishDetail:
    """重新启用被停用的菜品。与食材同一个理由：停用是软删除，就该退得回来。"""
    dish = get_dish(session, dish_id)
    if dish.is_active:
        return get_dish_detail(session, dish_id)

    dish.is_active = True
    session.flush()

    audit_service.record(
        session,
        entity_type=ENTITY_TYPE,
        entity_id=dish.id,
        action=AuditAction.UPDATE,
        actor_id=actor_id,
        actor_name=actor_name,
        after=_snapshot(dish),
        note=audit_note or "重新启用菜品",
    )
    session.commit()
    return get_dish_detail(session, dish_id)


def upsert_many_with_recipe(
    session: Session,
    rows: Sequence[dict[str, Any]],
    recipes: dict[str, RecipePayload],
) -> dict[str, int]:
    """批量导入专用。按名称新增或更新菜品，并按名称整体替换配方。

    与单条创建一样递增配方版本，但**不在导入过程中逐条重算营养**——
    导入完成后由调用方统一触发一次，避免边导入边算造成的重复开销。
    """
    counts = {"created": 0, "updated": 0, "recipe_replaced": 0}
    touched: list[Dish] = []
    created_ids: set[UUID] = set()

    for row in rows:
        name = str(row["name"])
        existing = repository.find_by_name(session, name)
        if existing is None:
            dish = Dish(**row)
            session.add(dish)
            session.flush()
            created_ids.add(dish.id)
            counts["created"] += 1
        else:
            changed = [field for field, value in row.items() if getattr(existing, field) != value]
            for field in changed:
                setattr(existing, field, row[field])
            if changed:
                counts["updated"] += 1
            dish = existing
        touched.append(dish)

    for dish in touched:
        recipe = recipes.get(dish.name)
        if recipe is None:
            continue
        _write_recipe(session, dish, recipe)
        # 新建的菜品版本从 1 起算；只有「在已有配方上再导入」才递增
        if dish.id not in created_ids:
            dish.recipe_version += 1
        counts["recipe_replaced"] += 1

    session.flush()
    return counts


def _validate_recipe(session: Session, payload: RecipePayload) -> None:
    ingredient_ids = [line.ingredient_id for line in payload.ingredients]
    found = repository.active_ids(session, ingredient_ids=ingredient_ids)
    missing = [str(item) for item in ingredient_ids if item not in found]
    if missing:
        raise BusinessRuleError(
            "配方里有食材不存在，请先在食材库中补齐", details={"missing": missing}
        )

    seasoning_ids = [line.seasoning_id for line in payload.seasonings]
    found_seasonings = repository.active_seasoning_ids(session, seasoning_ids=seasoning_ids)
    missing_seasonings = [str(item) for item in seasoning_ids if item not in found_seasonings]
    if missing_seasonings:
        raise BusinessRuleError(
            "配方里有调味料不存在，请先在调味料库中补齐",
            details={"missing": missing_seasonings},
        )


def _write_recipe(session: Session, dish: Dish, payload: RecipePayload) -> None:
    repository.replace_recipe(
        session,
        dish.id,
        ingredients=[
            IngredientLineValues(
                ingredient_id=line.ingredient_id,
                quantity_per_serving_g=line.quantity_per_serving_g,
                edible_ratio_override=line.edible_ratio_override,
                note=line.note,
            )
            for line in payload.ingredients
        ],
        seasonings=[
            SeasoningLineValues(
                seasoning_id=line.seasoning_id,
                quantity_per_serving_g=line.quantity_per_serving_g,
                note=line.note,
            )
            for line in payload.seasonings
        ],
    )


def _recipe_snapshot(session: Session, dish_id: UUID) -> dict[str, Any]:
    ingredient_rows, seasoning_rows = repository.load_recipe_rows(session, [dish_id])
    return {
        "ingredients": [
            {
                "name": ingredient.name,
                "quantity_g": str(item.quantity_per_serving_g),
                "edible_ratio_override": snapshot(item.edible_ratio_override),
            }
            for item, ingredient in ingredient_rows
        ],
        "seasonings": [
            {
                "name": seasoning.name,
                "quantity_g": str(item.quantity_per_serving_g),
            }
            for item, seasoning in seasoning_rows
        ],
    }


def _recipe_signature(session: Session, dish_id: UUID) -> tuple[tuple[Any, ...], ...]:
    """当前配方的可比较指纹。只比内容，不比主键与顺序。"""
    ingredient_rows, seasoning_rows = repository.load_recipe_rows(session, [dish_id])
    return (
        tuple(
            sorted(
                (
                    str(item.ingredient_id),
                    item.quantity_per_serving_g,
                    item.edible_ratio_override,
                )
                for item, _ in ingredient_rows
            )
        ),
        tuple(
            sorted(
                (str(item.seasoning_id), item.quantity_per_serving_g) for item, _ in seasoning_rows
            )
        ),
    )


def _payload_signature(payload: RecipePayload) -> tuple[tuple[Any, ...], ...]:
    return (
        tuple(
            sorted(
                (
                    str(line.ingredient_id),
                    line.quantity_per_serving_g,
                    line.edible_ratio_override,
                )
                for line in payload.ingredients
            )
        ),
        tuple(
            sorted(
                (str(line.seasoning_id), line.quantity_per_serving_g) for line in payload.seasonings
            )
        ),
    )


def _snapshot(dish: Dish) -> dict[str, Any]:
    return {
        "name": dish.name,
        "category": dish.category.value,
        "cooking_method": dish.cooking_method.value,
        "standard_serving_g": snapshot(dish.standard_serving_g),
        "servings_per_pot": snapshot(dish.servings_per_pot),
        "allergens": list(dish.allergens or []),
        "is_breakfast_staple": dish.is_breakfast_staple,
        "recipe_version": dish.recipe_version,
        "note": dish.note,
        "is_active": dish.is_active,
    }

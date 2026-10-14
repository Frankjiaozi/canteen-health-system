"""营养域的数据访问。

## 跨域读模型装配（全项目唯一的例外）

本模块是**读侧装配**：营养计算天然要横向读取 dish / ingredient / seasoning / menu /
collection 五个域的数据，把它们拼成引擎的输入结构。因此这里允许引用其它域的 ORM 模型，
这是全项目唯一一处这样的引用。

边界仍然清楚：**只读**。任何写入都走各域自己的 service，本模块不修改别的域的数据。
这样做的理由是不给每个输入都造一层 DTO——那只会增加间接层，并不隔离任何真实变化，
而营养计算与这些字段是天然绑定的。
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.modules.collection.models import DailyLog, DailyLogItem
from app.modules.dish.models import Dish, RecipeItem, RecipeSeasoning
from app.modules.ingredient.models import Ingredient
from app.modules.menu.models import MenuDay, MenuDayItem
from app.modules.nutrition.engine import (
    CalibrationSample,
    DishRecipe,
    IngredientInput,
    NutrientVector,
    RecipeIngredientLine,
    RecipeSeasoningLine,
    SeasoningInput,
)
from app.modules.nutrition.models import CalibrationFactor, DishNutrition
from app.modules.seasoning.models import Seasoning
from app.shared.enums import (
    CalibrationSource,
    CookingMethod,
    MealType,
    NutrientCaliber,
    NutritionValueType,
    SeasoningCategory,
)


def _to_ingredient_input(ingredient: Ingredient) -> IngredientInput:
    return IngredientInput(
        id=ingredient.id,
        name=ingredient.name,
        edible_ratio=ingredient.edible_ratio,
        energy_kcal=ingredient.energy_kcal,
        protein_g=ingredient.protein_g,
        fat_g=ingredient.fat_g,
        carb_g=ingredient.carb_g,
        sodium_mg=ingredient.sodium_mg,
        data_source=ingredient.data_source,
        source_version=ingredient.source_version,
    )


def _to_seasoning_input(seasoning: Seasoning) -> SeasoningInput:
    return SeasoningInput(
        id=seasoning.id,
        name=seasoning.name,
        category=seasoning.category,
        energy_kcal=seasoning.energy_kcal,
        protein_g=seasoning.protein_g,
        fat_g=seasoning.fat_g,
        carb_g=seasoning.carb_g,
        sodium_mg=seasoning.sodium_mg,
        data_source=seasoning.data_source,
    )


def load_recipes(session: Session, dish_ids: Sequence[UUID]) -> dict[UUID, DishRecipe]:
    """批量装配配方，避免逐道菜查询造成的 N+1。"""
    if not dish_ids:
        return {}

    dishes = session.scalars(select(Dish).where(Dish.id.in_(dish_ids))).all()

    ingredient_lines: dict[UUID, list[RecipeIngredientLine]] = defaultdict(list)
    ingredient_rows = session.execute(
        select(RecipeItem, Ingredient)
        .join(Ingredient, Ingredient.id == RecipeItem.ingredient_id)
        .where(RecipeItem.dish_id.in_(dish_ids))
        .order_by(RecipeItem.quantity_per_serving_g.desc())
    ).all()
    for recipe_item, ingredient in ingredient_rows:
        ingredient_lines[recipe_item.dish_id].append(
            RecipeIngredientLine(
                ingredient=_to_ingredient_input(ingredient),
                quantity_g=recipe_item.quantity_per_serving_g,
                edible_ratio_override=recipe_item.edible_ratio_override,
            )
        )

    seasoning_lines: dict[UUID, list[RecipeSeasoningLine]] = defaultdict(list)
    seasoning_rows = session.execute(
        select(RecipeSeasoning, Seasoning)
        .join(Seasoning, Seasoning.id == RecipeSeasoning.seasoning_id)
        .where(RecipeSeasoning.dish_id.in_(dish_ids))
        .order_by(RecipeSeasoning.quantity_per_serving_g.desc())
    ).all()
    for recipe_seasoning, seasoning in seasoning_rows:
        seasoning_lines[recipe_seasoning.dish_id].append(
            RecipeSeasoningLine(
                seasoning=_to_seasoning_input(seasoning),
                quantity_g=recipe_seasoning.quantity_per_serving_g,
            )
        )

    return {
        dish.id: DishRecipe(
            dish_id=dish.id,
            dish_name=dish.name,
            cooking_method=dish.cooking_method,
            recipe_version=dish.recipe_version,
            ingredients=tuple(ingredient_lines.get(dish.id, ())),
            seasonings=tuple(seasoning_lines.get(dish.id, ())),
        )
        for dish in dishes
    }


def load_menu_day(session: Session, on_date: date, meal_type: MealType) -> MenuDay | None:
    return session.scalar(
        select(MenuDay).where(MenuDay.date == on_date, MenuDay.meal_type == meal_type)
    )


def load_menu_dish_ids(session: Session, menu_day_id: UUID) -> list[UUID]:
    return list(
        session.scalars(select(MenuDayItem.dish_id).where(MenuDayItem.menu_day_id == menu_day_id))
    )


def load_daily_log(session: Session, on_date: date, meal_type: MealType) -> DailyLog | None:
    return session.scalar(
        select(DailyLog).where(DailyLog.date == on_date, DailyLog.meal_type == meal_type)
    )


def load_daily_log_items(session: Session, daily_log_id: UUID) -> dict[UUID, DailyLogItem]:
    items = session.scalars(
        select(DailyLogItem).where(DailyLogItem.daily_log_id == daily_log_id)
    ).all()
    return {item.dish_id: item for item in items}


def load_calibration_samples(
    session: Session, *, start: date, end: date
) -> list[CalibrationSample]:
    """把窗口内每一次采集拼成一个方程，供引擎拟合各烹饪方式的调料偏置。

    做法是两次查询后在内存里按餐次归并，而不是逐餐查一次——56 天会产生上百次往返，
    而这里的数据量本来就小。
    """
    logs = list(
        session.scalars(select(DailyLog).where(DailyLog.date >= start, DailyLog.date <= end)).all()
    )
    if not logs:
        return []

    log_ids = [log.id for log in logs]
    rows = session.execute(
        select(
            DailyLogItem.daily_log_id,
            Dish.cooking_method,
            Seasoning.category,
            func.sum(RecipeSeasoning.quantity_per_serving_g * DailyLogItem.servings_produced),
        )
        .join(Dish, Dish.id == DailyLogItem.dish_id)
        .join(RecipeSeasoning, RecipeSeasoning.dish_id == Dish.id)
        .join(Seasoning, Seasoning.id == RecipeSeasoning.seasoning_id)
        .where(DailyLogItem.daily_log_id.in_(log_ids))
        .group_by(DailyLogItem.daily_log_id, Dish.cooking_method, Seasoning.category)
    ).all()

    implied: dict[UUID, dict[CookingMethod, dict[SeasoningCategory, Decimal]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    for log_id, method, category, amount in rows:
        implied[log_id][method][category] = Decimal(amount or 0)

    samples: list[CalibrationSample] = []
    for log in logs:
        actual = {
            SeasoningCategory.EDIBLE_OIL: log.oil_total_g,
            SeasoningCategory.SALT: log.salt_total_g,
            SeasoningCategory.SUGAR: log.sugar_total_g,
        }
        samples.append(
            CalibrationSample(
                actual={category: value for category, value in actual.items() if value is not None},
                implied={
                    method: dict(categories)
                    for method, categories in implied.get(log.id, {}).items()
                },
            )
        )
    return samples


def list_menu_days_between(session: Session, start: date, end: date) -> list[MenuDay]:
    return list(
        session.scalars(
            select(MenuDay).where(MenuDay.date >= start, MenuDay.date <= end).order_by(MenuDay.date)
        )
    )


def list_menu_days_for_dish(session: Session, dish_id: UUID) -> list[MenuDay]:
    """这道菜被安排进过哪些菜单日。配方改动后按这个范围重算。"""
    return list(
        session.scalars(
            select(MenuDay)
            .join(MenuDayItem, MenuDayItem.menu_day_id == MenuDay.id)
            .where(MenuDayItem.dish_id == dish_id)
            .order_by(MenuDay.date, MenuDay.meal_type)
        )
    )


def upsert_dish_nutrition(
    session: Session,
    *,
    dish_id: UUID,
    on_date: date,
    meal_type: MealType,
    caliber: NutrientCaliber,
    value_type: NutritionValueType,
    nutrients: NutrientVector,
    uncertainty: dict[str, Any],
    trace: dict[str, Any],
    source_note: str,
) -> str:
    """按「菜品 + 日期 + 餐次 + 口径 + 数值类型」写入结果。

    同一口径下理论值与校准值分别存储，便于对比与回溯。
    """
    existing = session.scalar(
        select(DishNutrition).where(
            DishNutrition.dish_id == dish_id,
            DishNutrition.date == on_date,
            DishNutrition.meal_type == meal_type,
            DishNutrition.caliber == caliber,
            DishNutrition.value_type == value_type,
        )
    )

    values: dict[str, Any] = {
        **nutrients.as_dict(),
        "uncertainty": uncertainty,
        "computation_trace": trace,
        "source_note": source_note,
    }

    if existing is None:
        session.add(
            DishNutrition(
                dish_id=dish_id,
                date=on_date,
                meal_type=meal_type,
                caliber=caliber,
                value_type=value_type,
                **values,
            )
        )
        return "created"

    changed = [field for field, value in values.items() if getattr(existing, field) != value]
    for field in changed:
        setattr(existing, field, values[field])
    return "updated" if changed else "unchanged"


def count_nutritions(
    session: Session,
    *,
    on_date: date,
    caliber: NutrientCaliber,
    value_type: NutritionValueType,
) -> int:
    return len(
        session.scalars(
            select(DishNutrition.id).where(
                DishNutrition.date == on_date,
                DishNutrition.caliber == caliber,
                DishNutrition.value_type == value_type,
            )
        ).all()
    )


def replace_calibration_factors(
    session: Session,
    *,
    on_date: date,
    meal_type: MealType,
    cooking_method: CookingMethod,
    source: CalibrationSource,
    #: JSONB 列，值统一以字符串存入以免浮点误差（"1.18" / "0.9800"）
    coefficients: dict[str, Any],
    dish_id: UUID | None = None,
    basis_note: str | None = None,
    created_by: UUID | None = None,
) -> None:
    """写入一组系数。

    同一 (日期, 餐次, 烹饪方式, 来源, 菜品) 只保留一行——**替换语义由这里保证**，
    而不是靠数据库唯一约束：抽样那天可能测同一烹饪方式的几道菜，各带自己的
    `dish_id`，用唯一约束反而卡住了正当用法。
    """
    conditions = [
        CalibrationFactor.date == on_date,
        CalibrationFactor.meal_type == meal_type,
        CalibrationFactor.cooking_method == cooking_method,
        CalibrationFactor.source == source,
        CalibrationFactor.dish_id.is_(None)
        if dish_id is None
        else CalibrationFactor.dish_id == dish_id,
    ]
    session.execute(delete(CalibrationFactor).where(*conditions))
    session.add(
        CalibrationFactor(
            date=on_date,
            meal_type=meal_type,
            cooking_method=cooking_method,
            source=source,
            coefficients=coefficients,
            dish_id=dish_id,
            basis_note=basis_note,
            created_by=created_by,
        )
    )
    session.flush()


def load_calibration_factors(
    session: Session, *, on_date: date, meal_type: MealType
) -> list[CalibrationFactor]:
    return list(
        session.scalars(
            select(CalibrationFactor)
            .where(
                CalibrationFactor.date == on_date,
                CalibrationFactor.meal_type == meal_type,
            )
            .order_by(CalibrationFactor.source, CalibrationFactor.cooking_method)
        ).all()
    )


def latest_sampling_corrections(
    session: Session, *, cooking_method: CookingMethod, on_or_before: date
) -> tuple[dict[UUID, Decimal], Decimal | None]:
    """第三层抽样纠偏留下的整体系数，按「菜品级」与「烹饪方式级」分开返回。

    只取 `on_or_before` 当天及更早的：抽样是既有事实，不能反过来影响它之前的日子。
    同一个键下有多条时取最新的一条——纠偏是「我改主意了」，后测的覆盖先测的。

    菜品级优先于烹饪方式级：称的既然是这道菜，就信这道菜，不要用一个更大的平均值
    把它盖过去。返回值里的 `None` 键位置留给调用方表达「没有可用的烹饪方式级修正」。
    """
    rows = session.scalars(
        select(CalibrationFactor)
        .where(
            CalibrationFactor.source == CalibrationSource.SAMPLING,
            CalibrationFactor.cooking_method == cooking_method,
            CalibrationFactor.date <= on_or_before,
        )
        .order_by(CalibrationFactor.date, CalibrationFactor.created_at)
    ).all()

    by_dish: dict[UUID, Decimal] = {}
    by_method: Decimal | None = None
    for row in rows:
        value = row.coefficients.get("OVERALL")
        if value is None:
            continue
        # 按日期升序遍历，后写入的自然覆盖先写入的
        if row.dish_id is None:
            by_method = Decimal(str(value))
        else:
            by_dish[row.dish_id] = Decimal(str(value))
    return by_dish, by_method

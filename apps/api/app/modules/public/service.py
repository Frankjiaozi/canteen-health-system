"""公开大屏的内容装配。

这一层只做「把库里已经算好的真实结果拼成一份可展示的内容」，不重新计算营养值——
大屏上的数字必须与营养引擎落库的结果完全一致，不能是另算一遍得到的近似值。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.dish.models import Dish
from app.modules.nutrition.models import DishNutrition, NutritionStandard
from app.modules.public import repository
from app.modules.public.schemas import (
    NutrientValue,
    PublicBoard,
    PublicDishCard,
    StandardComparison,
)
from app.shared.enums import StandardCode
from app.shared.nutrients import (
    FIELD_TO_NUTRIENT_CODE,
    NUTRIENT_FIELDS,
    NUTRIENT_SCALES,
    NUTRIENT_UNITS,
)
from app.shared.standards import compare_to_standard, sum_per_capita_across_meals

DISCLAIMER = (
    "本屏只展示菜品级营养与群体级供给数据，不针对任何个人，也不构成任何医疗建议；"
    "对照基准引自《中国居民膳食指南（2022）》。"
)


def today() -> date:
    return datetime.now(get_settings().timezone).date()


def build_board(session: Session, *, on_date: date | None = None) -> PublicBoard:
    target_date = on_date or today()
    settings = get_settings()

    menu_day = repository.load_menu_day(session, target_date)
    dishes = repository.load_dishes(session, menu_day.id) if menu_day else []
    nutritions = repository.load_per_serving_nutritions(
        session, dish_ids=[dish.id for dish in dishes], on_date=target_date
    )
    daily_logs = repository.load_daily_logs(session, target_date)
    standards = repository.load_active_standards(session)

    # 没有营养结果的菜不上屏：与其显示一道没有数据的菜，不如不显示
    cards = [_dish_card(dish, nutritions[dish.id]) for dish in dishes if dish.id in nutritions]

    actuals: dict[StandardCode, Decimal | None] = {
        StandardCode.SALT: sum_per_capita_across_meals(daily_logs, "salt_total_g"),
        StandardCode.EDIBLE_OIL: sum_per_capita_across_meals(daily_logs, "oil_total_g"),
        StandardCode.ADDED_SUGAR: sum_per_capita_across_meals(daily_logs, "sugar_total_g"),
        StandardCode.FOOD_VARIETY: Decimal(
            repository.count_day_ingredients(session, on_date=target_date)
        ),
    }

    return PublicBoard(
        date=target_date,
        meal_label=menu_day.meal_type.label if menu_day else "未安排",
        generated_at=datetime.now(settings.timezone),
        diner_count=sum(log.diner_count for log in daily_logs) or None,
        dishes=cards,
        standards=[_standard_row(item, actuals.get(item.code)) for item in standards],
        disclaimer=DISCLAIMER,
    )


def _dish_card(dish: Dish, nutrition: DishNutrition) -> PublicDishCard:
    ranges = nutrition.uncertainty.get("ranges", {})
    nutrients = [
        NutrientValue(
            code=FIELD_TO_NUTRIENT_CODE[field].value,
            label=FIELD_TO_NUTRIENT_CODE[field].label,
            unit=NUTRIENT_UNITS[field],
            digits=NUTRIENT_SCALES[field],
            value=_fmt(getattr(nutrition, field), NUTRIENT_SCALES[field]),
            lower=str(ranges.get(field, {}).get("lower", _fmt(getattr(nutrition, field), 2))),
            upper=str(ranges.get(field, {}).get("upper", _fmt(getattr(nutrition, field), 2))),
        )
        for field in NUTRIENT_FIELDS
    ]

    return PublicDishCard(
        dish_id=dish.id,
        name=dish.name,
        category_label=dish.category.label,
        cooking_method_label=dish.cooking_method.label,
        standard_serving_g=str(dish.standard_serving_g),
        allergens=list(dish.allergens or []),
        nutrients=nutrients,
        recipe_version=dish.recipe_version,
        source_note=nutrition.source_note,
        missing_nutrients=list(nutrition.uncertainty.get("missing_nutrients", [])),
    )


def _standard_row(standard: NutritionStandard, actual: Decimal | None) -> StandardComparison:
    return StandardComparison(
        code=standard.code.value,
        label=standard.name,
        unit=standard.unit,
        target_min=_optional_str(standard.target_min),
        target_max=_optional_str(standard.target_max),
        actual=_optional_str(actual),
        status=compare_to_standard(
            target_min=standard.target_min, target_max=standard.target_max, actual=actual
        ),
        source=standard.source,
        source_quote=standard.source_quote,
    )


def _fmt(value: Decimal, digits: int) -> str:
    return str(value.quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP))


def _optional_str(value: Decimal | None) -> str | None:
    return None if value is None else str(value)

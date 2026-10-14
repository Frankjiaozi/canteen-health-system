"""「明日菜单与采购」——把推荐、预测、采购串成一件事（纯编排，不自己造数）。

三者的分工是这次改动的核心，写在这里省得以后翻代码去猜：

| 环节 | 谁做 | 输出 |
| --- | --- | --- |
| 做哪几道菜 | 推荐（整数规划） | 菜品集 + 营养差距 + 理由 |
| 各做多少份 | **预测**（同星期历史 × 日历修正） | 每道菜的份数 |
| 买多少料 | 由两者相乘得到 | 各食材/调味料的公斤数与金额 |

**份数由预测给，不由推荐算**：份数要看明天是不是放假、这道菜历史卖得怎么样，
推荐手里没有这些信息。但份数又必须参与营养评估（人均供给 = Σ单份营养 × 份数 ÷ 人次），
所以它是推荐的**输入**而不是输出。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from app.core.errors import BusinessRuleError
from app.core.logging import get_logger
from app.modules.forecast import service as forecast_service
from app.modules.menuplan.schemas import MenuPlanDish, MenuPlanResponse
from app.modules.recommendation import repository as recommendation_repository
from app.modules.recommendation import service as recommendation_service
from app.shared.enums import MealType
from sqlalchemy.orm import Session

logger = get_logger(__name__)

#: 预测不出来时的基准份数怎么取：按每人一份估。
#: 这不是「建议做这么多」，只是在拿不到预测时保证采购量还能算出来，并在页面上标出来。
FALLBACK_SERVINGS_PER_DINER = Decimal("1")


def build_menu_plan(
    session: Session,
    *,
    on_date: date,
    meal_type: MealType = MealType.LUNCH,
    diner_count: int | None = None,
) -> MenuPlanResponse:
    """生成明天的菜单与采购建议。"""
    candidate_ids = recommendation_service.candidate_dish_ids(session)
    if not candidate_ids:
        raise BusinessRuleError("没有可用于推荐的菜品：菜品需要有配方，并且至少供应过一次")

    diners = diner_count or recommendation_repository.load_latest_diner_count(
        session, on_date=on_date
    )

    # 先预测：逐菜独立，所以不必先知道菜单就能算出每道菜的份数
    prediction = forecast_service.predict_dishes(
        session, on_date=on_date, meal_type=meal_type, dish_ids=candidate_ids
    )
    fallback_servings = Decimal(diners) * FALLBACK_SERVINGS_PER_DINER
    servings_by_dish = {
        dish_id: prediction.servings.get(dish_id, fallback_servings) for dish_id in candidate_ids
    }

    # 再推荐：拿预测份数当营养评估基准，只回答「做哪几道菜」
    suggestion = recommendation_service.generate(
        session,
        on_date=on_date,
        meal_type=meal_type,
        diner_count=diners,
        servings_by_dish=servings_by_dish,
    )

    recommended_ids = [UUID(dish.dish_id) for dish in suggestion.dishes]
    forecast_service.persist_predictions(
        session,
        prediction,
        on_date=on_date,
        meal_type=meal_type,
        only=frozenset(recommended_ids),
    )
    session.commit()

    requirements, total_cost = forecast_service.build_purchase_list(
        session,
        servings_by_dish={dish_id: servings_by_dish[dish_id] for dish_id in recommended_ids},
    )

    dishes = [
        MenuPlanDish(
            dish_id=dish.dish_id,
            dish_name=dish.dish_name,
            category_label=dish.category_label,
            cooking_method_label=dish.cooking_method_label,
            energy_kcal=dish.energy_kcal,
            salt_g=dish.salt_g,
            popularity=dish.popularity,
            nutrition_basis=dish.nutrition_basis,
            predicted_servings=(
                None
                if UUID(dish.dish_id) not in prediction.servings
                else str(prediction.servings[UUID(dish.dish_id)])
            ),
            predicted_basis_label=next(
                (row.basis_label for row in prediction.dishes if row.dish_id == UUID(dish.dish_id)),
                None,
            ),
            prediction_fallback=UUID(dish.dish_id) not in prediction.servings,
        )
        for dish in suggestion.dishes
    ]

    fallback_names = [dish.dish_name for dish in dishes if dish.prediction_fallback]
    notes = [
        "菜品由推荐在营养目标下选出；份数由预测按同星期历史与日历修正给出。",
        "推荐用预测份数评估营养，因此页面上只有一套份数。",
    ]
    if fallback_names:
        notes.append(
            "这几道菜历史不足、预测不出份数，采购量按「每人一份」估算：" + "、".join(fallback_names)
        )
    logger.info(
        "菜单与采购：%s %s，%d 道菜，采购 %d 项，%s 元",
        on_date,
        meal_type.label,
        len(dishes),
        len(requirements),
        total_cost,
    )
    return MenuPlanResponse(
        date=on_date,
        meal_type=meal_type,
        meal_type_label=meal_type.label,
        diner_count=diners,
        suggestion_id=suggestion.id,
        dishes=dishes,
        gaps=suggestion.gaps,
        reasons=suggestion.reasons,
        requirements=requirements,
        total_cost=total_cost,
        budget=suggestion.budget,
        target_basis=suggestion.target_basis,
        missing_price_warning=suggestion.missing_price_warning,
        excluded_dishes=suggestion.excluded_dishes,
        calendar_notes=[prediction.calendar_note] if prediction.calendar_note else [],
        skipped_predictions=prediction.skipped,
        servings_note=(
            "采购量 = 推荐选出的菜 × 该菜明天的预测份数；"
            "预测不出来时退回「每人一份」估算并逐行标注。"
        ),
        notes=notes,
    )

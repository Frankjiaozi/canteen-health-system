"""只读的数据准备检查。说明缺口，不伪造记录，也不把结构完整当作真实性认证。"""

from datetime import date, datetime, timedelta
from typing import Literal
from uuid import UUID

from app.core.config import get_settings
from app.modules.collection.models import DailyLog
from app.modules.dish.models import RecipeItem, RecipeSeasoning
from app.modules.forecast import service as forecast
from app.modules.ingredient.models import Ingredient
from app.modules.menuplan.schemas import PlanReadiness, ReadinessCategory, ReadinessIssue
from app.modules.recommendation import repository
from app.modules.recommendation import service as recommendation
from app.modules.seasoning.models import Seasoning
from app.shared.enums import MealType
from sqlalchemy import select
from sqlalchemy.orm import Session

NUTRIENTS = {
    "energy_kcal": "能量",
    "protein_g": "蛋白质",
    "fat_g": "脂肪",
    "carb_g": "碳水化合物",
    "sodium_mg": "钠",
}


def inspect(
    session: Session,
    *,
    on_date: date,
    meal_type: MealType,
    excluded_dish_ids: frozenset[UUID] = frozenset(),
) -> PlanReadiness:
    dishes = repository.load_active_dishes(session)
    candidate_ids = set(
        recommendation.candidate_dish_ids(session, on_date=on_date, meal_type=meal_type)
    )
    previous = repository.load_previous_dishes(session, on_date=on_date, meal_type=meal_type)
    excluded = previous | set(excluded_dish_ids)
    available = candidate_ids - excluded
    start, end = on_date - timedelta(weeks=forecast.HISTORY_WEEKS), on_date - timedelta(days=1)
    records = session.scalars(
        select(DailyLog)
        .where(DailyLog.date.between(start, end), DailyLog.meal_type == meal_type)
        .order_by(DailyLog.date.desc())
    ).all()
    latest = session.scalar(
        select(DailyLog)
        .where(DailyLog.date < on_date, DailyLog.meal_type == meal_type, DailyLog.diner_count > 0)
        .order_by(DailyLog.date.desc())
        .limit(1)
    )
    issues: list[ReadinessIssue] = []

    def add(
        code: str,
        severity: Literal["blocking", "warning"],
        title: str,
        detail: str,
        action: str,
        link: str,
        entity_id: str | None = None,
    ) -> None:
        issues.append(
            ReadinessIssue(
                code=code,
                severity=severity,
                title=title,
                detail=detail,
                action=action,
                link=link,
                entity_id=entity_id,
            )
        )

    categories = [
        ReadinessCategory(
            code=category.value,
            label=category.label,
            available_count=sum(dishes[key].category == category for key in available),
            required_minimum=minimum,
        )
        for category, minimum in recommendation.CATEGORY_MIN.items()
    ]
    if len(available) < recommendation.DISH_COUNT_MIN:
        add(
            "insufficient_candidates",
            "blocking",
            "可用候选菜不足",
            f"当前有 {len(available)} 道可用，菜单至少需要 {recommendation.DISH_COUNT_MIN} 道。候选须在用、有配方且有本餐次过去的出餐记录；前一日菜单和主动排除同时生效。",
            "补齐配方与真实历史，或减少主动排除；不要伪造历史来凑数。",
            "/admin/dishes",
        )
    calendar = forecast.repository.load_holiday(session, day=on_date)
    if calendar and not calendar.is_verified:
        add(
            "unverified_calendar",
            "warning",
            "目标日期的日历安排尚未核对",
            f"{calendar.date}：{calendar.name}。本次不会按这条未核对安排修正预测。",
            "对照正式校历或通知核对后，再重新生成。",
            "/admin/menu-plan",
        )
    for row in categories:
        if row.available_count < row.required_minimum:
            add(
                "missing_category",
                "blocking",
                f"缺少可用{row.label}",
                f"本餐至少需要 {row.required_minimum} 道{row.label}，目前可用 {row.available_count} 道。",
                "检查该类菜的配方、同餐次历史与排除条件。",
                "/admin/dishes",
            )
    unknown = excluded_dish_ids - set(dishes)
    if unknown:
        add(
            "invalid_exclusion",
            "blocking",
            "排除条件已失效",
            f"{len(unknown)} 个菜品不存在或已停用。",
            "刷新菜品库并重新选择排除条件。",
            "/admin/dishes",
        )
    recipe_ids = set(
        session.scalars(select(RecipeItem.dish_id).where(RecipeItem.dish_id.in_(dishes))).all()
    )
    without_recipe = [item.name for key, item in dishes.items() if key not in recipe_ids]
    if without_recipe:
        add(
            "missing_recipe",
            "warning",
            "部分在用菜没有食材配方",
            "、".join(sorted(without_recipe)),
            "在菜品与配方中补录真实单份用量。",
            "/admin/dishes",
        )
    prediction = forecast.predict_dishes(
        session, on_date=on_date, meal_type=meal_type, dish_ids=list(available)
    )
    predictable = available & set(prediction.servings)
    if available - predictable:
        names = sorted(dishes[key].name for key in available - predictable)
        add(
            "insufficient_history",
            "warning",
            "部分候选历史不足，份数将降级估算",
            "、".join(names),
            "核对过去 8 周本餐次的有效记录；无预测时仍会明确按每人一份估算。",
            "/admin/collection",
        )
    if not records:
        add(
            "no_recent_records",
            "warning",
            "最近 8 周没有本餐次记录",
            f"范围 {start} 至 {end}，{meal_type.label}。其他餐次不会混入预测。",
            "补充真实供餐记录；未营业无需编造数据。",
            "/admin/collection",
        )
    elif latest and (end - latest.date).days > 7:
        add(
            "stale_records",
            "warning",
            "有效人次记录距目标日期较远",
            f"最近为 {latest.date}，相距 {(on_date - latest.date).days} 天。",
            "核对这段时间是否营业，并显式设置预计人次。",
            "/admin/collection",
        )

    ingredient_rows = session.scalars(
        select(Ingredient)
        .join(RecipeItem, RecipeItem.ingredient_id == Ingredient.id)
        .where(RecipeItem.dish_id.in_(available))
        .distinct()
        .order_by(Ingredient.name)
    ).all()
    seasoning_rows = session.scalars(
        select(Seasoning)
        .join(RecipeSeasoning, RecipeSeasoning.seasoning_id == Seasoning.id)
        .where(RecipeSeasoning.dish_id.in_(available))
        .distinct()
        .order_by(Seasoning.name)
    ).all()
    missing_price = missing_nutrition = 0
    for rows, link in (
        (ingredient_rows, "/admin/ingredients"),
        (seasoning_rows, "/admin/seasonings"),
    ):
        for material in rows:
            if material.unit_price is None:
                missing_price += 1
                add(
                    "missing_price",
                    "warning",
                    f"{material.name} 缺少单价",
                    "该项无法计入完整预算，不能把已知部分合计当作总成本。",
                    "在原料库补录有依据的元/公斤市品单价。",
                    link,
                    str(material.id),
                )
            fields = [
                label for field, label in NUTRIENTS.items() if getattr(material, field) is None
            ]
            if fields:
                missing_nutrition += 1
                add(
                    "missing_nutrition",
                    "warning",
                    f"{material.name} 营养数据有缺项",
                    "缺少：" + "、".join(fields),
                    "核对营养数据来源；缺失不能按实际为零解释。",
                    link,
                    str(material.id),
                )
            if not material.is_active:
                add(
                    "inactive_material",
                    "warning",
                    f"配方仍引用已停用原料 {material.name}",
                    "停用状态不自动证明历史配方无效，但新计划需人工核对。",
                    "核对配方是否需要替换，并保留历史版本。",
                    link,
                    str(material.id),
                )
            if not (material.data_source or "").strip():
                add(
                    "missing_source",
                    "warning",
                    f"{material.name} 没有数据来源说明",
                    "无法从来源字段追溯这条原料数据。",
                    "补充实际来源与适用版本。",
                    link,
                    str(material.id),
                )
    issues.sort(key=lambda issue: (issue.severity != "blocking", issue.code, issue.title))
    return PlanReadiness(
        checked_at=datetime.now(get_settings().timezone).isoformat(),
        on_date=on_date,
        meal_type=meal_type,
        meal_type_label=meal_type.label,
        state="blocked"
        if any(row.severity == "blocking" for row in issues)
        else "attention"
        if issues
        else "ready",
        active_dish_count=len(dishes),
        candidate_count=len(candidate_ids),
        available_count=len(available),
        excluded_count=len(candidate_ids & excluded),
        predicted_count=len(predictable),
        history_start=start,
        history_end=end,
        history_record_count=len(records),
        days_with_records=len({row.date for row in records}),
        latest_record_date=latest.date if latest else None,
        latest_diner_count=latest.diner_count if latest else None,
        missing_price_count=missing_price,
        missing_nutrition_count=missing_nutrition,
        categories=categories,
        issues=issues[:100],
        issue_count=len(issues),
        truncated=len(issues) > 100,
        note="仅检查当前数据的结构与计算准备情况，不认证来源真实性、不保证求解有解或营养全部达标。缺口统计针对当前可用候选涉及的原料；历史按目标餐次、目标日期之前取数。",
    )

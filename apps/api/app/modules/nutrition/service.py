"""营养计算服务：装配输入 → 调用纯函数引擎 → 落库结果。

业务规则集中在这里，引擎保持无状态；两者的边界就是「引擎不碰数据库」。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.modules.nutrition import engine, repository
from app.modules.nutrition.engine import NutrientVector
from app.shared.enums import MealType, NutrientCaliber, NutritionValueType

logger = get_logger(__name__)

SOURCE_NOTE_PER_SERVING = "按标准配方推算的单份营养（三层校准第一层）"
SOURCE_NOTE_PER_CAPITA = "按标准配方推算的该菜人均摄入（三层校准第一层）"


@dataclass
class ComputeReport:
    """一次计算的写入统计，供调用方断言与输出。"""

    menu_days: int = 0
    dishes: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0

    def merge(self, other: ComputeReport) -> ComputeReport:
        return ComputeReport(
            menu_days=self.menu_days + other.menu_days,
            dishes=self.dishes + other.dishes,
            created=self.created + other.created,
            updated=self.updated + other.updated,
            unchanged=self.unchanged + other.unchanged,
        )

    def record(self, action: str) -> None:
        if action == "created":
            self.created += 1
        elif action == "updated":
            self.updated += 1
        else:
            self.unchanged += 1

    @property
    def rows(self) -> int:
        return self.created + self.updated + self.unchanged

    def describe(self) -> str:
        return (
            f"菜单日 {self.menu_days} 天，覆盖菜品 {self.dishes} 道；"
            f"营养结果共 {self.rows} 条（新增 {self.created}、更新 {self.updated}、"
            f"未变 {self.unchanged}）"
        )


def compute_menu_day(session: Session, *, on_date: date, meal_type: MealType) -> ComputeReport:
    """计算某天某一餐的全部营养结果。"""
    report = ComputeReport()

    menu_day = repository.load_menu_day(session, on_date, meal_type)
    if menu_day is None:
        return report
    report.menu_days = 1

    recipes = repository.load_recipes(session, repository.load_menu_dish_ids(session, menu_day.id))
    report.dishes = len(recipes)

    daily_log = repository.load_daily_log(session, on_date, meal_type)
    log_items = repository.load_daily_log_items(session, daily_log.id) if daily_log else {}

    for dish_id, recipe in recipes.items():
        result = engine.compute_theoretical_per_serving(recipe)

        report.record(
            repository.upsert_dish_nutrition(
                session,
                dish_id=dish_id,
                on_date=on_date,
                meal_type=meal_type,
                caliber=NutrientCaliber.PER_SERVING,
                value_type=NutritionValueType.THEORETICAL,
                nutrients=result.per_serving,
                uncertainty=_uncertainty_payload(
                    result.per_serving, missing_nutrients=result.missing_nutrients
                ),
                trace=result.trace,
                source_note=SOURCE_NOTE_PER_SERVING,
            )
        )

        item = log_items.get(dish_id)
        if daily_log is None or item is None:
            continue

        report.record(
            _store_per_capita(
                session,
                on_date=on_date,
                meal_type=meal_type,
                dish_id=dish_id,
                per_serving=result.per_serving,
                source_trace=result.trace,
                missing_nutrients=result.missing_nutrients,
                servings_produced=item.servings_produced,
                leftover_ratio=item.leftover_ratio,
                diner_count=daily_log.diner_count,
            )
        )

    session.flush()
    return report


def compute_recent_days(session: Session, *, days: int) -> ComputeReport:
    """计算最近若干天（含今天）的营养结果，用于准备演示数据。"""
    today = datetime.now(get_settings().timezone).date()
    start = today - timedelta(days=days - 1)

    total = ComputeReport()
    for menu_day in repository.list_menu_days_between(session, start, today):
        total = total.merge(
            compute_menu_day(session, on_date=menu_day.date, meal_type=menu_day.meal_type)
        )
    session.commit()
    logger.info("营养计算完成：%s", total.describe())
    return total


def recompute_dish_nutrition(session: Session, dish_id: UUID) -> ComputeReport:
    """重算某道菜在**所有供应过它的日子**里的营养结果。

    配方一改，历史结果不能只改最近一天——公开大屏看的是当天，
    而看板、抽样对比、预测回测看的都是历史，几处必须一起对齐。
    """
    menu_days = repository.list_menu_days_for_dish(session, dish_id)
    total = ComputeReport()
    for menu_day in menu_days:
        total = total.merge(
            compute_menu_day(session, on_date=menu_day.date, meal_type=menu_day.meal_type)
        )
    session.commit()
    return total


def preview_per_serving(session: Session, dish_ids: Sequence[UUID]) -> dict[UUID, NutrientVector]:
    """按当前配方现算单份营养，**不落库**。

    服务的是「还没被排进过菜单」的菜品：它没有 `dish_nutritions` 快照可读，
    但配方已经能算出营养值。单份理论值只取决于配方本身，与「哪天供应」无关，
    所以这里算出来的与将来落库的结果一致；区别只在于没有日期，也就不可追溯，
    因此只用于列表摘要这种即时展示，不作为正式结果。
    """
    previews: dict[UUID, NutrientVector] = {}
    for dish_id, recipe in repository.load_recipes(session, dish_ids).items():
        if not recipe.ingredients and not recipe.seasonings:
            # 没有配方明细就没有可算的东西，交给上层显示「无配方」
            continue
        previews[dish_id] = engine.compute_theoretical_per_serving(recipe).per_serving
    return previews


def _store_per_capita(
    session: Session,
    *,
    on_date: date,
    meal_type: MealType,
    dish_id: UUID,
    per_serving: NutrientVector,
    source_trace: dict[str, Any],
    missing_nutrients: tuple[str, ...],
    servings_produced: Decimal,
    leftover_ratio: Decimal | None,
    diner_count: int,
) -> str:
    per_capita = engine.compute_theoretical_per_capita(
        per_serving,
        servings_produced=servings_produced,
        leftover_ratio=leftover_ratio,
        diner_count=diner_count,
    )
    # 人均口径的区间比单份更宽：出餐份数、剩余比例与就餐人次本身都不精确
    extra = engine.PER_CAPITA_EXTRA_TOLERANCE
    trace: dict[str, Any] = {
        **source_trace,
        "caliber": NutrientCaliber.PER_CAPITA.value,
        "tolerance": {
            "base": str(engine.BASE_TOLERANCE),
            "applied": str(engine.tolerance_for(len(missing_nutrients), extra=extra)),
            "reason": f"在单份推算误差之上，再叠加份数、剩余比例与人次数量的估计误差 +{extra}",
        },
        "per_capita_basis": {
            "formula": "人均摄入 = 单份营养 × 出餐份数 × (1 − 剩余比例) ÷ 就餐人次",
            "per_serving": per_serving.as_trace(),
            "servings_produced": str(servings_produced),
            "leftover_ratio": None if leftover_ratio is None else str(leftover_ratio),
            "diner_count": diner_count,
        },
    }
    return repository.upsert_dish_nutrition(
        session,
        dish_id=dish_id,
        on_date=on_date,
        meal_type=meal_type,
        caliber=NutrientCaliber.PER_CAPITA,
        value_type=NutritionValueType.THEORETICAL,
        nutrients=per_capita,
        uncertainty=_uncertainty_payload(
            per_capita, missing_nutrients=missing_nutrients, extra_tolerance=extra
        ),
        trace=trace,
        source_note=SOURCE_NOTE_PER_CAPITA,
    )


def _uncertainty_payload(
    nutrients: NutrientVector,
    *,
    missing_nutrients: tuple[str, ...],
    extra_tolerance: Decimal = Decimal("0"),
) -> dict[str, Any]:
    ranges = engine.build_uncertainty(
        nutrients, missing_nutrients=missing_nutrients, extra_tolerance=extra_tolerance
    )
    return {
        "note": "第一层基准误差 ±15%，成分数据缺失时逐项放宽，人均口径另叠加份数与人次误差",
        "tolerance": str(engine.tolerance_for(len(missing_nutrients), extra=extra_tolerance)),
        "missing_nutrients": list(missing_nutrients),
        "ranges": {field: interval.as_dict() for field, interval in ranges.items()},
    }

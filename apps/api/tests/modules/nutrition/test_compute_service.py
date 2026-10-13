"""营养计算落库的集成测试。

这里验证的是「种子数据 → 读侧装配 → 引擎 → 数据库」整条链路，
期望值仍是**外部手算**出来的，不是从实现里反抄的。
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.modules.dish.models import Dish
from app.modules.menu.models import MenuDay
from app.modules.nutrition import service
from app.modules.nutrition.models import DishNutrition
from app.shared.enums import NutrientCaliber, NutritionValueType
from sqlalchemy import select
from sqlalchemy.orm import Session


def _latest_menu_day(session: Session) -> MenuDay:
    menu_day = session.scalar(select(MenuDay).order_by(MenuDay.date.desc()).limit(1))
    assert menu_day is not None, "需要先执行 pnpm db:seed 准备菜单数据"
    return menu_day


def _rows_for(session: Session, *, dish_name: str, caliber: NutrientCaliber) -> list[DishNutrition]:
    return list(
        session.scalars(
            select(DishNutrition)
            .join(Dish, Dish.id == DishNutrition.dish_id)
            .where(Dish.name == dish_name, DishNutrition.caliber == caliber)
        )
    )


def test_compute_creates_both_calibers(db_session: Session) -> None:
    menu_day = _latest_menu_day(db_session)

    report = service.compute_menu_day(
        db_session, on_date=menu_day.date, meal_type=menu_day.meal_type
    )

    assert report.dishes == 4  # 主食 + 当日轮换的三道菜
    assert report.rows == report.dishes * 2, "每道菜都应有单份与人均两条结果"


def test_persisted_per_serving_matches_independent_hand_calculation(db_session: Session) -> None:
    """米饭配方：大米 80 克、无调味料，可食部比例 1.0。

    能量 0.8×346=276.8、蛋白质 0.8×7.4=5.92、脂肪 0.8×0.8=0.64、
    碳水 0.8×77.9=62.32、钠 0.8×3.8=3.04。
    """
    rows = _rows_for(db_session, dish_name="米饭", caliber=NutrientCaliber.PER_SERVING)
    assert rows, "米饭的单份营养结果应当已写入"

    row = rows[0]
    assert row.energy_kcal == Decimal("276.80")
    assert row.protein_g == Decimal("5.920")
    assert row.fat_g == Decimal("0.640")
    assert row.carb_g == Decimal("62.320")
    assert row.sodium_mg == Decimal("3.04")
    assert row.value_type is NutritionValueType.THEORETICAL
    assert row.source_note is not None and "第一层" in row.source_note


def test_per_serving_and_per_capita_are_stored_separately(db_session: Session) -> None:
    """两个口径必须各存一条，混用会得出完全错误的结论。"""
    per_serving = _rows_for(db_session, dish_name="米饭", caliber=NutrientCaliber.PER_SERVING)
    per_capita = _rows_for(db_session, dish_name="米饭", caliber=NutrientCaliber.PER_CAPITA)

    assert per_serving and per_capita
    assert per_serving[0].id != per_capita[0].id
    assert per_serving[0].energy_kcal != per_capita[0].energy_kcal
    assert per_serving[0].caliber is NutrientCaliber.PER_SERVING
    assert per_capita[0].caliber is NutrientCaliber.PER_CAPITA


def test_per_capita_is_consistent_with_its_stored_basis(db_session: Session) -> None:
    """人均值必须能由快照里记录的份数、剩餐比例与人次重新算出来。

    这条断言保护的是「可追溯」这件事本身：快照不能只是摆设，
    它记录的依据必须真的能还原出库里的数值。
    """
    rows = _rows_for(db_session, dish_name="米饭", caliber=NutrientCaliber.PER_CAPITA)
    assert rows, "米饭的人均营养结果应当已写入"

    row = rows[0]
    basis = row.computation_trace["per_capita_basis"]
    servings = Decimal(str(basis["servings_produced"]))
    leftover = Decimal(str(basis["leftover_ratio"]))
    diner_count = Decimal(str(basis["diner_count"]))
    per_serving_energy = Decimal(str(basis["per_serving"]["energy_kcal"]))

    expected = (per_serving_energy * servings * (Decimal("1") - leftover) / diner_count).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    assert row.energy_kcal == expected


def test_trace_records_recipe_snapshot_and_missing_data(db_session: Session) -> None:
    rows = _rows_for(db_session, dish_name="番茄炒蛋", caliber=NutrientCaliber.PER_SERVING)
    assert rows

    trace = rows[0].computation_trace
    assert trace["engine"] == "nutrition.theoretical"
    assert trace["recipe_version"] == 1
    ingredient_names = {item["name"] for item in trace["ingredients"]}
    assert {"番茄", "鸡蛋"} <= ingredient_names
    seasoning_names = {item["name"] for item in trace["seasonings"]}
    assert {"大豆油", "食盐", "白砂糖"} <= seasoning_names
    # 演示数据里成分齐全，不该出现缺失项
    assert rows[0].uncertainty["missing_nutrients"] == []
    # 149.38 × 0.85 = 126.973 → 126.97；149.38 × 1.15 = 171.787 → 171.79
    assert rows[0].uncertainty["ranges"]["energy_kcal"]["lower"] == "126.97"
    assert rows[0].uncertainty["ranges"]["energy_kcal"]["upper"] == "171.79"


def test_recompute_is_idempotent(db_session: Session) -> None:
    menu_day = _latest_menu_day(db_session)

    service.compute_menu_day(db_session, on_date=menu_day.date, meal_type=menu_day.meal_type)
    second = service.compute_menu_day(
        db_session, on_date=menu_day.date, meal_type=menu_day.meal_type
    )

    assert second.created == 0
    assert second.updated == 0
    assert second.unchanged == second.rows > 0


def test_uncertainty_is_never_a_bare_point_value(db_session: Session) -> None:
    """系统给出区间而不是看似精确的点值，每个数值都要有上下界。"""
    # 先按当前配方重算一遍，避免读到历史遗留的行
    menu_day = _latest_menu_day(db_session)
    service.compute_menu_day(db_session, on_date=menu_day.date, meal_type=menu_day.meal_type)

    rows = list(db_session.scalars(select(DishNutrition).limit(20)))
    assert rows

    for row in rows:
        ranges = row.uncertainty["ranges"]
        for field in ("energy_kcal", "protein_g", "fat_g", "carb_g", "sodium_mg"):
            lower = Decimal(str(ranges[field]["lower"]))
            upper = Decimal(str(ranges[field]["upper"]))
            assert lower <= getattr(row, field) <= upper, f"{field} 的区间没有包住数值本身"

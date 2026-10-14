"""第三层 抽样纠偏。

第一层按配方推算，第二层用当日油盐糖实际用量把推算拉回现实；两层都建立在
「配方写对了」这个前提上。第三层就是来检验这个前提的：称一份菜，看实测与
推算差多少，把差额归给调味料，反推出一个整体系数。

三条硬断言：

1. **反推系数与手算一致**——用一条独立的 SQL 重算食材部分与调味料部分的能量，
   再按「(实测 − 食材) ÷ 调味料」算一遍，结果必须等于接口给出的系数；
2. **差额超出调味料能解释的范围时不套用系数**——只落实测证据并标记疑似配方有误。
   这一条是整套校准里最后的防线：硬套一个 3 倍系数，等于把一个错配方「校准」成
   一个看起来自洽的错值，比不校准更糟；
3. **抽样结果按 SAMPLED 落库，误差区间随实测收敛**——实测只有 2% 偏差，
   就不该继续挂着 15% 的理论区间，否则「承认了多少把握」这件事就失真了。
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from app.modules.dish.models import Dish
from app.modules.menu.models import MenuDay, MenuDayItem
from app.modules.nutrition.models import CalibrationFactor, DishNutrition
from app.shared.enums import (
    CalibrationSource,
    MealType,
    NutrientCaliber,
    NutritionValueType,
)
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

SAMPLES = "/api/v1/calibration/samples"
COMPARISON = "/api/v1/calibration/comparison"
DAILY_CLOSURE = "/api/v1/calibration/daily-closure"

#: 演示种子里配方较完整、含四类调味料的一道菜
DISH = "土豆炖牛肉"


def _dish(session: Session, name: str) -> Dish:
    dish = session.scalar(select(Dish).where(Dish.name == name))
    assert dish is not None, f"演示种子里应当有「{name}」"
    return dish


def _served_day(session: Session, dish_name: str) -> MenuDay:
    """找一天确实供应了这道菜的菜单日——对比接口要三个值同时存在，日期必须对得上。"""
    menu_day = session.scalar(
        select(MenuDay)
        .join(MenuDayItem, MenuDayItem.menu_day_id == MenuDay.id)
        .join(Dish, Dish.id == MenuDayItem.dish_id)
        .where(Dish.name == dish_name, MenuDay.meal_type == MealType.LUNCH)
        .order_by(MenuDay.date.desc())
        .limit(1)
    )
    assert menu_day is not None, f"演示历史里应当有供应过「{dish_name}」的日子"
    return menu_day


def _theoretical(session: Session, *, dish_id: UUID, on_date: date) -> DishNutrition:
    session.expire_all()
    row = session.scalar(
        select(DishNutrition).where(
            DishNutrition.dish_id == dish_id,
            DishNutrition.date == on_date,
            DishNutrition.meal_type == MealType.LUNCH,
            DishNutrition.caliber == NutrientCaliber.PER_SERVING,
            DishNutrition.value_type == NutritionValueType.THEORETICAL,
        )
    )
    assert row is not None, "这道菜当天应当已有理论值结果"
    return row


def _sql_parts(session: Session, dish_id: UUID) -> tuple[Decimal, Decimal]:
    """独立重算「食材部分能量」与「调味料部分能量」，不经过引擎。

    食材按可食部折算（配方覆盖值优先），调味料按每 100 克成分直接折算。
    """
    ingredient_energy = session.scalar(
        text(
            """
            SELECT COALESCE(SUM(
                ri.quantity_per_serving_g
                * COALESCE(ri.edible_ratio_override, i.edible_ratio)
                / 100 * i.energy_kcal
            ), 0)
            FROM recipe_items ri
            JOIN ingredients i ON i.id = ri.ingredient_id
            WHERE ri.dish_id = :dish
            """
        ),
        {"dish": dish_id},
    )
    seasoning_energy = session.scalar(
        text(
            """
            SELECT COALESCE(SUM(rs.quantity_per_serving_g / 100 * s.energy_kcal), 0)
            FROM recipe_seasonings rs
            JOIN seasonings s ON s.id = rs.seasoning_id
            WHERE rs.dish_id = :dish
            """
        ),
        {"dish": dish_id},
    )
    return Decimal(str(ingredient_energy)), Decimal(str(seasoning_energy))


def _rounded_parts(theoretical: DishNutrition) -> tuple[Decimal, Decimal]:
    """从理论值快照里取引擎实际用到的「食材部分」与「调味料合计」。

    引擎把两块各自取整到两位小数后再相加，因此拿未取整的 SQL 原值去反推，
    会在第四位小数上对不上——这不是系数算错，是取整口径的差别。
    """
    trace = theoretical.computation_trace
    ingredient = Decimal(trace["ingredient_part"]["energy_kcal"])
    seasoning = sum(Decimal(vector["energy_kcal"]) for vector in trace["seasoning_part"].values())
    return ingredient, seasoning


def _sampling_factor_count(session: Session, dish_id: UUID) -> int:
    """这道菜身上现有多少条抽样纠偏系数——用于断言「有没有多写一条」。"""
    session.expire_all()
    return (
        session.scalar(
            select(func.count())
            .select_from(CalibrationFactor)
            .where(
                CalibrationFactor.dish_id == dish_id,
                CalibrationFactor.source == CalibrationSource.SAMPLING,
            )
        )
        or 0
    )


def test_derived_factor_matches_hand_calculation(
    as_recorder: TestClient, db_session: Session
) -> None:
    """反推系数 = (实测能量 − 食材能量) ÷ 调味料能量，这里独立算一遍比对。"""
    dish = _dish(db_session, DISH)
    menu_day = _served_day(db_session, DISH)
    theoretical = _theoretical(db_session, dish_id=dish.id, on_date=menu_day.date)

    ingredient_energy, seasoning_energy = _sql_parts(db_session, dish.id)
    ingredient_rounded, seasoning_rounded = _rounded_parts(theoretical)

    # 快照里的食材/调味料拆分必须与独立重算一致，否则下面的系数就是照着一个错基准算的
    assert ingredient_rounded == ingredient_energy.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    assert seasoning_rounded == seasoning_energy.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    assert seasoning_energy > 0, "这道菜必须有调味料，否则测不出「只缩放调味料」这件事"

    # 故意让实测比推算多吃了 1.2 倍的调味料贡献
    measured_energy = ingredient_rounded + Decimal("1.2") * seasoning_rounded
    response = as_recorder.post(
        SAMPLES,
        json={
            "dish_id": str(dish.id),
            "date": menu_day.date.isoformat(),
            "meal_type": "LUNCH",
            "measured_energy_kcal": str(measured_energy),
            "measured_protein_g": str(theoretical.protein_g),
            "measured_fat_g": str(theoretical.fat_g),
            "measured_carb_g": str(theoretical.carb_g),
            "measured_sodium_mg": str(theoretical.sodium_mg),
            "scope": "DISH",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert Decimal(body["overall_factor"]) == Decimal("1.2000")
    assert body["applied"] is True
    assert body["suspect_recipe"] is False


def test_absurd_deviation_is_flagged_and_not_applied(
    as_recorder: TestClient, db_session: Session
) -> None:
    """实测能量高出推算六倍——这不是多放了油，是配方录错了。"""
    dish = _dish(db_session, DISH)
    menu_day = _served_day(db_session, DISH)
    theoretical = _theoretical(db_session, dish_id=dish.id, on_date=menu_day.date)
    ingredient_rounded, seasoning_rounded = _rounded_parts(theoretical)
    factors_before = _sampling_factor_count(db_session, dish.id)

    body = as_recorder.post(
        SAMPLES,
        json={
            "dish_id": str(dish.id),
            "date": menu_day.date.isoformat(),
            "meal_type": "LUNCH",
            "measured_energy_kcal": str(ingredient_rounded + Decimal("6") * seasoning_rounded),
            "measured_protein_g": str(theoretical.protein_g),
            "measured_fat_g": str(theoretical.fat_g),
            "measured_carb_g": str(theoretical.carb_g),
            "measured_sodium_mg": str(theoretical.sodium_mg),
            "scope": "DISH",
        },
    ).json()

    assert body["applied"] is False
    assert body["suspect_recipe"] is True
    assert "配方" in body["note"], "要告诉录入员去看配方，而不是只说一句不适用"
    assert Decimal(body["overall_factor"]) > Decimal("2.0")

    # 实测证据要留下，否则这条异常数据就白测了
    sampled = db_session.scalar(
        select(DishNutrition).where(
            DishNutrition.dish_id == dish.id,
            DishNutrition.date == menu_day.date,
            DishNutrition.value_type == NutritionValueType.SAMPLED,
        )
    )
    assert sampled is not None
    assert sampled.computation_trace["suspect_recipe"] is True

    # 但系数绝不能写进去
    assert _sampling_factor_count(db_session, dish.id) == factors_before, (
        "疑似配方有误时不得写入系数"
    )


def test_sample_stored_as_sampled_with_tighter_interval(
    as_recorder: TestClient, db_session: Session
) -> None:
    """实测与推算吻合时，抽样结果的误差区间应当比理论基准明显收窄。"""
    dish = _dish(db_session, DISH)
    menu_day = _served_day(db_session, DISH)
    theoretical = _theoretical(db_session, dish_id=dish.id, on_date=menu_day.date)

    as_recorder.post(
        SAMPLES,
        json={
            "dish_id": str(dish.id),
            "date": menu_day.date.isoformat(),
            "meal_type": "LUNCH",
            "measured_energy_kcal": str(theoretical.energy_kcal),
            "measured_protein_g": str(theoretical.protein_g),
            "measured_fat_g": str(theoretical.fat_g),
            "measured_carb_g": str(theoretical.carb_g),
            "measured_sodium_mg": str(theoretical.sodium_mg),
            "scope": "DISH",
        },
    )

    db_session.expire_all()
    sampled = db_session.scalar(
        select(DishNutrition).where(
            DishNutrition.dish_id == dish.id,
            DishNutrition.date == menu_day.date,
            DishNutrition.value_type == NutritionValueType.SAMPLED,
        )
    )
    assert sampled is not None
    assert sampled.source_note is not None and "第三层" in sampled.source_note

    sampled_tolerance = Decimal(sampled.uncertainty["tolerance"])
    theoretical_tolerance = Decimal(theoretical.uncertainty["tolerance"])
    assert sampled_tolerance <= Decimal("0.05")
    assert sampled_tolerance < theoretical_tolerance, "实测都吻合了，区间不该还挂着理论基准"


def test_comparison_exposes_three_values(as_recorder: TestClient, db_session: Session) -> None:
    """三个口径的来源要能并排看到，这是「校准值不是新真值」的界面基础。"""
    dish = _dish(db_session, DISH)
    menu_day = _served_day(db_session, DISH)
    theoretical = _theoretical(db_session, dish_id=dish.id, on_date=menu_day.date)

    as_recorder.post(
        DAILY_CLOSURE, params={"on_date": menu_day.date.isoformat(), "meal_type": "LUNCH"}
    )
    as_recorder.post(
        SAMPLES,
        json={
            "dish_id": str(dish.id),
            "date": menu_day.date.isoformat(),
            "meal_type": "LUNCH",
            "measured_energy_kcal": str(theoretical.energy_kcal),
            "measured_protein_g": str(theoretical.protein_g),
            "measured_fat_g": str(theoretical.fat_g),
            "measured_carb_g": str(theoretical.carb_g),
            "measured_sodium_mg": str(theoretical.sodium_mg),
            "scope": "DISH",
        },
    )

    body = as_recorder.get(
        COMPARISON,
        params={
            "dish_id": str(dish.id),
            "on_date": menu_day.date.isoformat(),
            "meal_type": "LUNCH",
        },
    ).json()

    assert body["theoretical"] is not None
    assert body["calibrated"] is not None
    assert body["sampled"] is not None
    assert body["sampled"]["energy_kcal"] == body["theoretical"]["energy_kcal"]


def test_cooking_method_scope_stores_factor_without_dish(
    as_recorder: TestClient, db_session: Session
) -> None:
    """抽样也可以用来纠正一整类烹饪方式，这时系数不带 dish_id。"""
    dish = _dish(db_session, DISH)
    menu_day = _served_day(db_session, DISH)
    theoretical = _theoretical(db_session, dish_id=dish.id, on_date=menu_day.date)

    as_recorder.post(
        SAMPLES,
        json={
            "dish_id": str(dish.id),
            "date": menu_day.date.isoformat(),
            "meal_type": "LUNCH",
            "measured_energy_kcal": str(theoretical.energy_kcal),
            "measured_protein_g": str(theoretical.protein_g),
            "measured_fat_g": str(theoretical.fat_g),
            "measured_carb_g": str(theoretical.carb_g),
            "measured_sodium_mg": str(theoretical.sodium_mg),
            "scope": "COOKING_METHOD",
        },
    )

    db_session.expire_all()
    stored = db_session.scalars(
        select(CalibrationFactor).where(
            CalibrationFactor.date == menu_day.date,
            CalibrationFactor.meal_type == MealType.LUNCH,
            CalibrationFactor.cooking_method == dish.cooking_method,
            CalibrationFactor.source == CalibrationSource.SAMPLING,
            # 只认「针对整类烹饪方式」的那一行；单菜抽样另有 dish_id，不在此列
            CalibrationFactor.dish_id.is_(None),
        )
    ).all()

    assert len(stored) == 1
    assert set(stored[0].coefficients) == {"OVERALL"}


def test_school_admin_cannot_record_sample(
    as_school_admin: TestClient, db_session: Session
) -> None:
    dish = _dish(db_session, DISH)
    menu_day = _served_day(db_session, DISH)

    response = as_school_admin.post(
        SAMPLES,
        json={
            "dish_id": str(dish.id),
            "date": menu_day.date.isoformat(),
            "meal_type": "LUNCH",
            "measured_energy_kcal": "200",
            "measured_protein_g": "10",
            "measured_fat_g": "5",
            "measured_carb_g": "20",
            "measured_sodium_mg": "500",
        },
    )

    assert response.status_code == 403


def test_dish_without_recipe_is_rejected(as_recorder: TestClient, db_session: Session) -> None:
    """没配方的菜没有比对基准，要给一句能照做的提示。"""
    created = as_recorder.post(
        "/api/v1/dishes",
        json={
            "name": "测试用无配方菜",
            "category": "STAPLE",
            "cooking_method": "STEAM",
            "standard_serving_g": "100",
            "servings_per_pot": "1",
        },
    )
    assert created.status_code == 201, created.text
    dish_id = created.json()["id"]

    response = as_recorder.post(
        SAMPLES,
        json={
            "dish_id": dish_id,
            "date": "2026-10-14",
            "meal_type": "LUNCH",
            "measured_energy_kcal": "200",
            "measured_protein_g": "10",
            "measured_fat_g": "5",
            "measured_carb_g": "20",
            "measured_sodium_mg": "500",
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "business_rule_violated"
    assert "配方" in response.json()["message"]


def test_sampled_rows_do_not_overwrite_theoretical(
    as_recorder: TestClient, db_session: Session
) -> None:
    """抽样是新增一个口径，不是覆盖理论值——三个值要能同时存在于库里。"""
    dish = _dish(db_session, DISH)
    menu_day = _served_day(db_session, DISH)
    theoretical = _theoretical(db_session, dish_id=dish.id, on_date=menu_day.date)

    as_recorder.post(
        DAILY_CLOSURE, params={"on_date": menu_day.date.isoformat(), "meal_type": "LUNCH"}
    )
    as_recorder.post(
        SAMPLES,
        json={
            "dish_id": str(dish.id),
            "date": menu_day.date.isoformat(),
            "meal_type": "LUNCH",
            "measured_energy_kcal": str(theoretical.energy_kcal),
            "measured_protein_g": str(theoretical.protein_g),
            "measured_fat_g": str(theoretical.fat_g),
            "measured_carb_g": str(theoretical.carb_g),
            "measured_sodium_mg": str(theoretical.sodium_mg),
            "scope": "DISH",
        },
    )

    db_session.expire_all()
    kinds = set(
        db_session.scalars(
            select(DishNutrition.value_type).where(
                DishNutrition.dish_id == dish.id, DishNutrition.date == menu_day.date
            )
        )
    )
    assert {
        NutritionValueType.THEORETICAL,
        NutritionValueType.CALIBRATED,
        NutritionValueType.SAMPLED,
    } <= kinds

    # 理论值一个字都没变
    again = _theoretical(db_session, dish_id=dish.id, on_date=menu_day.date)
    assert again.energy_kcal == theoretical.energy_kcal
    assert again.computation_trace["layer"] == "标准配方推算"


def test_repeated_sample_does_not_duplicate_rows(
    as_recorder: TestClient, db_session: Session
) -> None:
    """同一天同一道菜重复抽样，只更新那一行——落库键是全字段唯一约束。"""
    dish = _dish(db_session, DISH)
    menu_day = _served_day(db_session, DISH)
    theoretical = _theoretical(db_session, dish_id=dish.id, on_date=menu_day.date)

    payload = {
        "dish_id": str(dish.id),
        "date": menu_day.date.isoformat(),
        "meal_type": "LUNCH",
        "measured_energy_kcal": str(theoretical.energy_kcal),
        "measured_protein_g": str(theoretical.protein_g),
        "measured_fat_g": str(theoretical.fat_g),
        "measured_carb_g": str(theoretical.carb_g),
        "measured_sodium_mg": str(theoretical.sodium_mg),
        "scope": "DISH",
    }
    as_recorder.post(SAMPLES, json=payload)
    payload["measured_energy_kcal"] = str(theoretical.energy_kcal + Decimal("5"))
    as_recorder.post(SAMPLES, json=payload)

    db_session.expire_all()
    count = db_session.scalar(
        select(func.count())
        .select_from(DishNutrition)
        .where(
            DishNutrition.dish_id == dish.id,
            DishNutrition.date == menu_day.date,
            DishNutrition.value_type == NutritionValueType.SAMPLED,
        )
    )
    assert count == 1

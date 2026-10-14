"""第二层 当日闭环校准。

两条硬断言：

1. **系数与手算一致**——用一条独立的 SQL 直接算「配方用量 × 出餐份数」，再与实际用量相除，
   结果必须等于接口给出的系数；
2. **只缩放调味料贡献**——配方里没有调味料的菜（米饭、馒头），校准值必须与理论值**分毫不差**。
   这一条是「只缩放调味料」这个决定最锋利的守卫：整菜缩放会把米饭也一起抬高。
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.db import seed as seed_module
from app.modules.dish.models import Dish
from app.modules.menu.models import MenuDay, MenuDayItem
from app.modules.nutrition import engine
from app.modules.nutrition.models import DishNutrition
from app.shared.enums import (
    CookingMethod,
    MealType,
    NutrientCaliber,
    NutritionValueType,
    SeasoningCategory,
)
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

DAILY_CLOSURE = "/api/v1/calibration/daily-closure"
FACTORS = "/api/v1/calibration/factors"


def _latest_menu_day(session: Session) -> MenuDay:
    menu_day = session.scalar(select(MenuDay).order_by(MenuDay.date.desc()).limit(1))
    assert menu_day is not None, "需要先执行 pnpm db:seed 准备数据"
    return menu_day


def _recent_day_serving(session: Session, dish_name: str) -> MenuDay:
    """找一天确实供应了某道菜的菜单日。

    主食池是米饭/馒头轮换，「今天有没有米饭」并不确定——用例必须先查，不能假设。
    """
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


def _nutrient(session: Session, *, dish_name: str, value_type: NutritionValueType) -> Decimal:
    """按菜品名与数值类型取单份能量。"""
    session.expire_all()
    value = session.scalar(
        select(DishNutrition.energy_kcal)
        .join(Dish, Dish.id == DishNutrition.dish_id)
        .where(
            Dish.name == dish_name,
            DishNutrition.caliber == NutrientCaliber.PER_SERVING,
            DishNutrition.value_type == value_type,
        )
        .limit(1),
    )
    assert value is not None, f"没找到 {dish_name} 的 {value_type} 结果"
    return value


def test_closure_runs_and_stores_both_calibers(
    as_recorder: TestClient, db_session: Session
) -> None:
    menu_day = _latest_menu_day(db_session)

    response = as_recorder.post(
        DAILY_CLOSURE, params={"on_date": menu_day.date.isoformat(), "meal_type": "LUNCH"}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["factors"], "当天应当至少有一种烹饪方式被校准"
    assert body["calibrated_rows"] > 0

    calibers = set(
        db_session.scalars(
            select(DishNutrition.value_type).where(DishNutrition.date == menu_day.date)
        )
    )
    # 理论值与校准值并存，校准不覆盖理论值
    assert NutritionValueType.THEORETICAL in calibers
    assert NutritionValueType.CALIBRATED in calibers


def test_coefficient_matches_independent_hand_calculation(
    as_recorder: TestClient, db_session: Session
) -> None:
    """系数必须还原出种子数据里那套**已知偏置**。

    这是整个营养模块里唯一一条「真值已知」的检验。种子按「炒 1.18 / 炖 1.06 / 煮 0.95 /
    蒸 0 / 凉拌 1.0」的乘数生成每天的用油量，盐、糖各用一个统一乘数（见 `seed.py`），
    因此窗口拟合的结果可以直接和这套真值逐项对照。

    这里刻意**从种子模块读真值**而不是把数字抄进测试：抄一遍的话，哪天种子改了偏置，
    测试还拿着旧数字绿灯，那就成了摆设。

    也说清以前那条测试错在哪：它用「当日实际 ÷ 当日推算」重算了一遍——那是实现本身的
    公式，公式错了它跟着错，只能证明实现自洽，证明不了公式对。而那个公式在数学上根本
    无解（一天只有一个总量，却有多种烹饪方式同时在用同一种调料）。
    """
    menu_day = _latest_menu_day(db_session)

    body = as_recorder.post(
        DAILY_CLOSURE, params={"on_date": menu_day.date.isoformat(), "meal_type": "LUNCH"}
    ).json()

    assert body["window"]["samples"] >= 21, "演示历史应当够做一次按方法的分组拟合"
    assert body["window"]["fallback_reason"] is None

    by_method = {row["cooking_method"]: row for row in body["factors"]}
    for method, coefficients in by_method.items():
        expected_oil = Decimal(str(seed_module._OIL_BIAS_BY_METHOD[CookingMethod(method)]))
        if "EDIBLE_OIL" in coefficients["coefficients"]:
            got = Decimal(coefficients["coefficients"]["EDIBLE_OIL"])
            assert abs(got - expected_oil) <= Decimal("0.01"), (
                f"{method} 用油系数拟合为 {got}，种子真值 {expected_oil}"
            )
        for code, truth in (("SALT", seed_module._SALT_BIAS), ("SUGAR", seed_module._SUGAR_BIAS)):
            if code not in coefficients["coefficients"]:
                continue
            got = Decimal(coefficients["coefficients"][code])
            assert abs(got - Decimal(str(truth))) <= Decimal("0.01"), (
                f"{method} 的 {code} 拟合为 {got}，种子真值 {truth}"
            )


def test_daily_totals_are_a_check_not_a_multiplier(
    as_recorder: TestClient, db_session: Session
) -> None:
    """当天总量改成校验项：拿拟合系数预测当天用量，偏差写进 checks。

    这条守住的是「当天总量不再充当乘数」——那正是把系数算成三倍、十三倍的根源。
    """
    menu_day = _latest_menu_day(db_session)

    body = as_recorder.post(
        DAILY_CLOSURE, params={"on_date": menu_day.date.isoformat(), "meal_type": "LUNCH"}
    ).json()

    checks = {row["code"]: row for row in body["checks"]}
    assert set(checks) == {"EDIBLE_OIL", "SALT", "SUGAR"}
    for row in checks.values():
        actual = Decimal(row["actual_g"])
        predicted = Decimal(row["predicted_g"])
        assert actual > 0 and predicted > 0
        expected = ((actual - predicted) / predicted).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )
        assert Decimal(row["deviation"]) == expected
        assert row["status"] in {"ok", "warn"}

    # 种子数据是按同一套偏置生成的，预测应当贴得很紧
    assert all(row["status"] == "ok" for row in checks.values()), body["checks"]
    assert Decimal(body["window"]["residual_mape"]) <= Decimal("0.01")


def test_only_seasoning_contribution_is_scaled(
    as_recorder: TestClient, db_session: Session
) -> None:
    """配方里没有调味料的菜，校准值必须与理论值完全相同。

    这是「只缩放调味料」最锋利的守卫：如果哪天有人图省事改成整菜乘系数，
    米饭的能量会被凭空抬高——这条会立刻红。
    """
    menu_day = _recent_day_serving(db_session, "米饭")
    as_recorder.post(
        DAILY_CLOSURE, params={"on_date": menu_day.date.isoformat(), "meal_type": "LUNCH"}
    )

    theoretical = _nutrient(db_session, dish_name="米饭", value_type=NutritionValueType.THEORETICAL)
    calibrated = _nutrient(db_session, dish_name="米饭", value_type=NutritionValueType.CALIBRATED)

    assert calibrated == theoretical, "米饭不含调味料，校准不该动它一分一毫"


def test_dish_with_seasoning_does_change(as_recorder: TestClient, db_session: Session) -> None:
    """反过来：含调味料的菜必须真的被改动了，否则说明校准根本没生效。"""
    menu_day = _recent_day_serving(db_session, "土豆炖牛肉")
    as_recorder.post(
        DAILY_CLOSURE, params={"on_date": menu_day.date.isoformat(), "meal_type": "LUNCH"}
    )

    theoretical = _nutrient(
        db_session, dish_name="土豆炖牛肉", value_type=NutritionValueType.THEORETICAL
    )
    calibrated = _nutrient(
        db_session, dish_name="土豆炖牛肉", value_type=NutritionValueType.CALIBRATED
    )

    assert calibrated != theoretical, "含油盐糖的菜应当被校准修正"


def test_factors_can_be_listed(as_recorder: TestClient, db_session: Session) -> None:
    menu_day = _latest_menu_day(db_session)
    as_recorder.post(
        DAILY_CLOSURE, params={"on_date": menu_day.date.isoformat(), "meal_type": "LUNCH"}
    )

    rows = as_recorder.get(
        FACTORS, params={"on_date": menu_day.date.isoformat(), "meal_type": "LUNCH"}
    ).json()

    assert rows
    assert all(row["source"] == "DAILY_CLOSURE" for row in rows)
    assert all(row["cooking_method_label"] for row in rows)


def test_school_admin_cannot_run_calibration(
    as_school_admin: TestClient, db_session: Session
) -> None:
    menu_day = _latest_menu_day(db_session)

    response = as_school_admin.post(
        DAILY_CLOSURE, params={"on_date": menu_day.date.isoformat(), "meal_type": "LUNCH"}
    )

    assert response.status_code == 403


def test_day_without_menu_is_reported_clearly(as_recorder: TestClient) -> None:
    """没菜单的日子校准没有意义，要给一句能照做的提示，而不是静默返回空。"""
    response = as_recorder.post(
        DAILY_CLOSURE, params={"on_date": "2020-01-01", "meal_type": "LUNCH"}
    )

    assert response.status_code == 422
    assert response.json()["code"] == "business_rule_violated"
    assert "菜单" in response.json()["message"]


# ---------------------------------------------------------------------------
# 拟合算法本身（纯函数，不碰数据库）
# ---------------------------------------------------------------------------
def _samples(rows: list[tuple[float, float, float]]) -> list[engine.CalibrationSample]:
    """每行 = (炒菜推算油量, 炖菜推算油量, 当天实际油量)。"""
    return [
        engine.CalibrationSample(
            actual={SeasoningCategory.EDIBLE_OIL: Decimal(str(actual))},
            implied={
                CookingMethod.STIR_FRY: {SeasoningCategory.EDIBLE_OIL: Decimal(str(stir))},
                CookingMethod.STEW: {SeasoningCategory.EDIBLE_OIL: Decimal(str(stew))},
            },
        )
        for stir, stew, actual in rows
    ]


def test_fit_recovers_known_coefficients() -> None:
    """造一组「炒 1.2、炖 0.8」的数据，拟合必须把它们解出来。"""
    rows = [
        (100.0, 200.0, 100 * 1.2 + 200 * 0.8),
        (300.0, 100.0, 300 * 1.2 + 100 * 0.8),
        (120.0, 480.0, 120 * 1.2 + 480 * 0.8),
        (250.0, 350.0, 250 * 1.2 + 350 * 0.8),
    ] * 6  # 凑够最小样本数

    fitted = engine.fit_calibration_coefficients(_samples(rows))

    assert fitted.fallback_reason is None
    assert abs(
        fitted.coefficients[CookingMethod.STIR_FRY][SeasoningCategory.EDIBLE_OIL] - Decimal("1.2")
    ) <= Decimal("0.01")
    assert abs(
        fitted.coefficients[CookingMethod.STEW][SeasoningCategory.EDIBLE_OIL] - Decimal("0.8")
    ) <= Decimal("0.01")
    assert fitted.residual_mape <= Decimal("0.01")


def test_fit_falls_back_when_history_is_too_short() -> None:
    """样本不够时退化成整餐一个比值，并如实标注原因，而不是硬解出一组数。"""
    rows = [(100.0, 200.0, 100 * 1.2 + 200 * 0.8)] * 5  # 只有 5 天

    fitted = engine.fit_calibration_coefficients(_samples(rows))

    assert fitted.fallback_reason is not None
    assert SeasoningCategory.EDIBLE_OIL in fitted.fallbacks
    assert "少于" in fitted.fallbacks[SeasoningCategory.EDIBLE_OIL]
    stir = fitted.coefficients[CookingMethod.STIR_FRY][SeasoningCategory.EDIBLE_OIL]
    stew = fitted.coefficients[CookingMethod.STEW][SeasoningCategory.EDIBLE_OIL]
    assert stir == stew, "退化之后各方法应当是同一个比值，而不是各解各的"
    # 每天实际 280 克，推算 100 + 200 = 300 克，比值 280 ÷ 300
    assert abs(stir - Decimal("280") / Decimal("300")) <= Decimal("0.001")


def test_fit_falls_back_when_only_one_method_uses_the_seasoning() -> None:
    """只有一种烹饪方式在用这类调料时，按方法分组没有意义。"""
    samples = [
        engine.CalibrationSample(
            actual={SeasoningCategory.EDIBLE_OIL: Decimal("120")},
            implied={CookingMethod.STIR_FRY: {SeasoningCategory.EDIBLE_OIL: Decimal(str(100 + i))}},
        )
        for i in range(30)
    ]

    fitted = engine.fit_calibration_coefficients(samples)

    assert fitted.fallback_reason is not None
    assert "只有一种烹饪方式" in fitted.fallbacks[SeasoningCategory.EDIBLE_OIL]


def test_fit_never_returns_negative_coefficients() -> None:
    """某些日子实际用量明显低于推算量时，无约束最小二乘会解出负数；必须被截住。

    负系数会把一道菜的油量算成负的，落库时直接被 CHECK 约束挡下——宁可截到 0，
    也不要写进去一个物理上不存在的数。
    """
    rows = [
        (100.0, 200.0, 10.0),
        (300.0, 100.0, 20.0),
        (120.0, 480.0, 15.0),
        (250.0, 350.0, 30.0),
    ] * 6

    fitted = engine.fit_calibration_coefficients(_samples(rows))

    for by_category in fitted.coefficients.values():
        for value in by_category.values():
            assert value >= 0, "系数不能为负"


def test_fit_reports_zero_residual_when_the_model_is_exact() -> None:
    """每天的账都能被这套系数平掉时，残差应当是 0——否则这条残差指标就失去了意义。"""
    rows = [
        (float(stir), float(stew), stir * 1.2 + stew * 0.8)
        for stir, stew in (
            (100, 200),
            (300, 100),
            (120, 480),
            (250, 350),
            (400, 60),
            (90, 510),
        )
    ] * 5

    fitted = engine.fit_calibration_coefficients(_samples(rows))

    assert fitted.residual_mape <= Decimal("0.001")

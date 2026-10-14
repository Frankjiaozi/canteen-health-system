"""第二层 当日闭环校准。

两条硬断言：

1. **系数与手算一致**——用一条独立的 SQL 直接算「配方用量 × 出餐份数」，再与实际用量相除，
   结果必须等于接口给出的系数；
2. **只缩放调味料贡献**——配方里没有调味料的菜（米饭、馒头），校准值必须与理论值**分毫不差**。
   这一条是「只缩放调味料」这个决定最锋利的守卫：整菜缩放会把米饭也一起抬高。
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.modules.collection.models import DailyLog
from app.modules.dish.models import Dish
from app.modules.menu.models import MenuDay, MenuDayItem
from app.modules.nutrition.models import DishNutrition
from app.shared.enums import MealType, NutrientCaliber, NutritionValueType
from fastapi.testclient import TestClient
from sqlalchemy import select, text
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
    """系数 = 当日实际用量 ÷ 按配方推算的用量，这里用一条独立 SQL 重算一遍。"""
    menu_day = _latest_menu_day(db_session)
    daily_log = db_session.scalar(
        select(DailyLog).where(
            DailyLog.date == menu_day.date, DailyLog.meal_type == menu_day.meal_type
        )
    )
    assert daily_log is not None

    body = as_recorder.post(
        DAILY_CLOSURE, params={"on_date": menu_day.date.isoformat(), "meal_type": "LUNCH"}
    ).json()

    for row in body["factors"]:
        method = row["cooking_method"]
        for code, coefficient in row["coefficients"].items():
            theoretical = Decimal(row["theoretical_g"][code])
            actual = row["actual_g"][code]
            if actual is None or theoretical <= 0:
                assert Decimal(coefficient) == Decimal("1"), "拿不到实际用量的类别不该被缩放"
                continue

            # 独立重算：直接查「配方用量 × 出餐份数」，不经过服务层
            recomputed = db_session.scalar(
                text(
                    """
                    SELECT COALESCE(SUM(rs.quantity_per_serving_g * dli.servings_produced), 0)
                    FROM recipe_seasonings rs
                    JOIN seasonings s ON s.id = rs.seasoning_id
                    JOIN dishes d ON d.id = rs.dish_id
                    JOIN daily_log_items dli ON dli.dish_id = d.id
                    JOIN daily_logs dl ON dl.id = dli.daily_log_id
                    WHERE dl.date = :day
                      AND dl.meal_type = :meal
                      AND d.cooking_method = :method
                      AND s.category = :category
                    """
                ),
                {
                    "day": menu_day.date,
                    "meal": menu_day.meal_type.value,
                    "method": method,
                    "category": code,
                },
            )

            assert theoretical == Decimal(str(recomputed)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            ), f"{method} 的 {code} 推算用量与独立重算不一致"

            expected = (Decimal(actual) / theoretical).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            )
            assert Decimal(coefficient) == expected


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

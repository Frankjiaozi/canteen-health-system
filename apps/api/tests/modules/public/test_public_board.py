"""公开大屏接口的行为约定。

最要紧的一条：**不带任何 Cookie 也能访问**。这是全系统唯一免登录的接口，
需求里的「学生端」就是它。
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from app.modules.dish.models import Dish
from app.modules.menu.models import MenuDay, MenuDayItem
from app.modules.nutrition.models import DishNutrition
from app.modules.public import service
from app.shared.enums import NutrientCaliber, NutritionValueType
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

BASE = "/api/v1/public/board/today"


def _today_menu(session: Session) -> MenuDay:
    menu_day = session.scalar(select(MenuDay).order_by(MenuDay.date.desc()).limit(1))
    assert menu_day is not None, "需要先执行 pnpm db:seed 准备菜单数据"
    return menu_day


def test_board_is_accessible_without_login(client: TestClient) -> None:
    response = client.get(BASE)

    assert response.status_code == 200, "公开大屏不能要求登录"
    body = response.json()
    assert body["dishes"], "当天应当有可展示的菜品"
    assert body["meal_label"]
    assert body["disclaimer"]


def test_board_does_not_leak_personal_data(client: TestClient) -> None:
    """公开大屏只暴露菜品级营养与群体级数据。"""
    text = client.get(BASE).text

    for forbidden in ("username", "password", "student", "student_id", "phone"):
        assert forbidden not in text.lower()


def test_dish_nutrition_matches_stored_results(client: TestClient, db_session: Session) -> None:
    """大屏上的数字必须与营养引擎落库的结果一致，不能是另算一遍的近似值。"""
    body = client.get(BASE).json()
    menu_day = _today_menu(db_session)

    stored = {
        # 接口下发的 dish_id 是字符串，这里统一成字符串键再比对
        str(row.dish_id): row
        for row in db_session.scalars(
            select(DishNutrition).where(
                DishNutrition.date == menu_day.date,
                DishNutrition.caliber == NutrientCaliber.PER_SERVING,
                DishNutrition.value_type == NutritionValueType.THEORETICAL,
            )
        )
    }

    assert stored
    for card in body["dishes"]:
        row = stored.get(card["dish_id"])
        assert row is not None, f"大屏展示了没有营养结果的菜品：{card['name']}"
        by_code = {item["code"]: item for item in card["nutrients"]}
        assert by_code["ENERGY"]["value"] == str(row.energy_kcal)
        assert by_code["PROTEIN"]["value"] == str(row.protein_g)
        assert by_code["FAT"]["value"] == str(row.fat_g)
        assert by_code["CARBOHYDRATE"]["value"] == str(row.carb_g)
        assert by_code["SODIUM"]["value"] == str(row.sodium_mg)


def test_every_card_carries_an_uncertainty_range(client: TestClient) -> None:
    """系统给区间而不是看似精确的点值，这里连展示层也要保证。"""
    body = client.get(BASE).json()

    for card in body["dishes"]:
        for nutrient in card["nutrients"]:
            lower = Decimal(nutrient["lower"])
            upper = Decimal(nutrient["upper"])
            value = Decimal(nutrient["value"])
            assert lower <= value <= upper, f"{card['name']} 的 {nutrient['label']} 区间不成立"


def test_dishes_without_nutrition_are_hidden(client: TestClient, db_session: Session) -> None:
    menu_day = _today_menu(db_session)
    served = set(
        db_session.scalars(
            select(Dish.name)
            .join(MenuDayItem, MenuDayItem.dish_id == Dish.id)
            .where(MenuDayItem.menu_day_id == menu_day.id)
        )
    )
    shown = {card["name"] for card in client.get(BASE).json()["dishes"]}

    assert shown <= served
    assert shown == served, "演示数据下每道菜都应当有营养结果"


def test_standards_compare_against_daily_targets(client: TestClient) -> None:
    standards = {item["code"]: item for item in client.get(BASE).json()["standards"]}

    assert {"SALT", "EDIBLE_OIL", "ADDED_SUGAR", "FOOD_VARIETY"} <= set(standards)
    salt = standards["SALT"]
    assert salt["target_max"] == "5.000"
    assert salt["source"] == "《中国居民膳食指南（2022）》"
    assert salt["source_quote"] == "每天摄入食盐不超过5克"
    assert salt["status"] in {"ok", "over"}


def test_board_can_be_queried_for_other_dates(client: TestClient) -> None:
    response = client.get(BASE, params={"on_date": "2020-01-01"})

    assert response.status_code == 200
    body = response.json()
    assert body["date"] == "2020-01-01"
    # 没安排菜单的日期返回空内容，而不是 500
    assert body["dishes"] == []
    assert body["meal_label"] == "未安排"


def test_invalid_date_is_rejected(client: TestClient) -> None:
    response = client.get(BASE, params={"on_date": "not-a-date"})

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


# ---------------------------------------------------------------------------
# 纯逻辑
# ---------------------------------------------------------------------------
def test_per_capita_sums_each_meal_against_its_own_diner_count() -> None:
    """各餐人次不同，必须先各自除以本餐人次再相加。

    先加总量再除一次会算成另一件事：午餐 500 人吃 1000 克、晚餐 100 人吃 400 克，
    正确的人均日摄入是 2.0 + 4.0 = 6.0 克，而不是 1400 ÷ 600 ≈ 2.33 克。
    """
    logs = [
        SimpleNamespace(diner_count=500, salt_total_g=Decimal("1000")),
        SimpleNamespace(diner_count=100, salt_total_g=Decimal("400")),
    ]

    assert service._sum_per_capita(logs, "salt_total_g") == Decimal("6.00")


def test_per_capita_ignores_meals_without_diners() -> None:
    logs = [SimpleNamespace(diner_count=0, salt_total_g=Decimal("100"))]

    assert service._sum_per_capita(logs, "salt_total_g") is None

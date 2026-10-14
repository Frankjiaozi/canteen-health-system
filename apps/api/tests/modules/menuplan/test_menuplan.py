"""「明日菜单与采购」的行为约定。

这个接口是三个域的**编排**：推荐选菜、预测给份数、两者相乘得到采购量。
所以用例盯的不是「算法对不对」（那两组各有自己的用例），而是三件容易出错的事：

1. **份数口径**：采购量必须等于「推荐选出的菜 × 该菜明天的预测份数」，
   不能顺手用推荐那边的份数、也不能退回「每人一份」蒙一个数；
2. **采购单的可用性**：单位是公斤、按金额从大到小排、没单价的不占前排；
3. **拿不到份数时不装**：预测不出来的菜如实标注并说明采购按什么算的。
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from app.modules.dish.models import RecipeItem, RecipeSeasoning
from app.modules.forecast import service as forecast_service
from app.modules.forecast.models import Forecast
from app.modules.ingredient.models import Ingredient
from app.modules.seasoning.models import Seasoning
from app.shared.enums import IngredientCategory, MealType
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.helpers import today_local

BASE = "/api/v1/menu-plan"


def _per_serving_usage(session: Session, dish_id: UUID) -> list[tuple[str, Decimal]]:
    """从配方表直接读一道菜的单份用料（克）。

    刻意不调 `forecast.repository.load_ingredient_usage`：那样等于用被测代码
    验被测代码。这里读原始配方表，才能验证「份数乘得对不对」。
    """
    items = session.execute(
        select(Ingredient.name, RecipeItem.quantity_per_serving_g)
        .join(Ingredient, Ingredient.id == RecipeItem.ingredient_id)
        .where(RecipeItem.dish_id == dish_id)
    ).all()
    seasonings = session.execute(
        select(Seasoning.name, RecipeSeasoning.quantity_per_serving_g)
        .join(Seasoning, Seasoning.id == RecipeSeasoning.seasoning_id)
        .where(RecipeSeasoning.dish_id == dish_id)
    ).all()
    return [(name, Decimal(quantity)) for name, quantity in (*items, *seasonings)]


def _expected_quantities(
    session: Session, *, dishes: list[dict[str, object]], servings_key: str, fallback: Decimal
) -> dict[str, Decimal]:
    """按「单份用量 × 份数」手算出每种料的公斤数。"""
    totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for dish in dishes:
        raw = dish[servings_key]
        servings = fallback if raw is None else Decimal(str(raw))
        for name, per_serving in _per_serving_usage(session, UUID(str(dish["dish_id"]))):
            totals[name] += per_serving * servings
    return {
        name: (grams / Decimal("1000")).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        for name, grams in totals.items()
    }


# ---------------------------------------------------------------------------
# 接口
# ---------------------------------------------------------------------------
def test_purchase_list_is_recommended_dishes_times_predicted_servings(
    as_recorder: TestClient, db_session: Session
) -> None:
    """份数口径：采购量 = 推荐选出的菜 × 该菜明天的预测份数。（本次改动的核心）"""
    target = today_local() + timedelta(days=1)

    body = as_recorder.post(
        f"{BASE}/generate", params={"on_date": target.isoformat(), "meal_type": "LUNCH"}
    ).json()

    db_session.expire_all()
    assert body["dishes"], "演示数据下应当能推荐出菜品"
    assert body["requirements"], "采购建议不该是空的"
    assert body["date"] == target.isoformat()
    assert body["diner_count"] > 0
    # 推荐只回答「做哪几道菜」：份数不在推荐的结果里，页面上只有一套份数
    assert all("servings" not in dish for dish in body["dishes"])
    assert all(dish["predicted_servings"] for dish in body["dishes"])
    assert not body["skipped_predictions"], "有 8 周历史时不该有预测不出来的菜"

    expected = _expected_quantities(
        db_session, dishes=body["dishes"], servings_key="predicted_servings", fallback=Decimal("0")
    )
    actual = {row["name"]: Decimal(row["quantity"]) for row in body["requirements"]}

    assert actual == expected, "采购量必须由「预测份数」算出来"

    # 金额也要与逐项单价对得上，否则「合计」会和明细自相矛盾
    priced = [row for row in body["requirements"] if row["estimated_cost"] is not None]
    assert priced, "演示数据里应当有带单价的食材"
    assert Decimal(body["total_cost"]) == sum(
        (Decimal(row["estimated_cost"]) for row in priced), Decimal("0")
    ).quantize(Decimal("0.01"))


def test_purchase_list_reads_in_kg_and_by_amount(
    as_recorder: TestClient,
) -> None:
    """采购单是拿去下单的：单位是公斤，最贵的排最前。"""
    target = today_local() + timedelta(days=1)

    body = as_recorder.post(
        f"{BASE}/generate", params={"on_date": target.isoformat(), "meal_type": "LUNCH"}
    ).json()

    rows = body["requirements"]
    assert all(row["unit"] == "公斤" for row in rows)
    # 公斤的量级：单份几十克的料乘几百份，落到个位数公斤，不可能是 43101.6
    assert all(Decimal(row["quantity"]) < Decimal("1000") for row in rows)

    costs = [Decimal(row["estimated_cost"] or "0") for row in rows]
    unpriced = [row["estimated_cost"] is None for row in rows]
    # 有价的分在前、按金额降序；无价的整体沉底
    assert unpriced == sorted(unpriced), "没有单价的料应当排在最后"
    assert costs == sorted(costs, reverse=True), "采购单应按金额从大到小排"


def test_servings_note_says_where_the_numbers_come_from(
    as_recorder: TestClient,
) -> None:
    """看的人必须知道「买多少」是怎么来的，所以接口要把口径写出来。"""
    target = today_local() + timedelta(days=1)

    body = as_recorder.post(
        f"{BASE}/generate", params={"on_date": target.isoformat(), "meal_type": "LUNCH"}
    ).json()

    assert "预测份数" in body["servings_note"]
    assert body["notes"], "至少要有说明菜品与份数各自由谁决定"


def test_prediction_supplies_the_servings_the_dishes_are_planned_with(
    as_recorder: TestClient, db_session: Session
) -> None:
    """推荐用来评估营养的份数，就是页面上显示的那一套（不存在第二个份数）。"""
    target = today_local() + timedelta(days=1)

    body = as_recorder.post(
        f"{BASE}/generate", params={"on_date": target.isoformat(), "meal_type": "LUNCH"}
    ).json()

    db_session.expire_all()
    _, total_cost = forecast_service.build_purchase_list(
        db_session,
        servings_by_dish={
            UUID(dish["dish_id"]): Decimal(dish["predicted_servings"]) for dish in body["dishes"]
        },
    )
    assert Decimal(body["total_cost"]) == Decimal(str(total_cost))


def test_prediction_fallback_is_flagged_instead_of_hidden(
    as_recorder: TestClient, db_session: Session
) -> None:
    """历史窗口里没有数据时不装：如实标注，并写明采购量按什么算。

    取一个 8 周历史窗口之外的日期——那一天根本无从预测，正好把「预测不出来」这条路走通。
    """
    target = today_local() + timedelta(days=120)
    diners = 300

    body = as_recorder.post(
        f"{BASE}/generate",
        params={"on_date": target.isoformat(), "meal_type": "LUNCH", "diner_count": diners},
    ).json()

    assert body["dishes"], "预测不出来不影响推荐选菜"
    assert body["skipped_predictions"], "应当如实列出预测不出来的菜"
    assert all(dish["prediction_fallback"] for dish in body["dishes"])
    assert all(dish["predicted_servings"] is None for dish in body["dishes"])
    assert any("每人一份" in note for note in body["notes"])

    db_session.expire_all()
    expected = _expected_quantities(
        db_session,
        dishes=body["dishes"],
        servings_key="predicted_servings",
        fallback=Decimal(diners),
    )
    actual = {row["name"]: Decimal(row["quantity"]) for row in body["requirements"]}
    assert actual == expected, "退回基准份数时采购量仍要算得出来，并与之吻合"


def test_budget_follows_the_per_person_allowance(
    as_recorder: TestClient, db_session: Session
) -> None:
    """预算 = 人均预算 × 人次，不能与推荐那边各算一套。"""
    from app.core.config import get_settings

    target = today_local() + timedelta(days=1)
    diners = 400

    body = as_recorder.post(
        f"{BASE}/generate",
        params={"on_date": target.isoformat(), "meal_type": "LUNCH", "diner_count": diners},
    ).json()

    expected = (Decimal(str(get_settings().nutrition_meal_budget_per_person)) * diners).quantize(
        Decimal("0.01")
    )
    assert Decimal(body["budget"]) == expected
    assert body["gaps"], "营养差距要跟着一起给出来"
    assert body["reasons"], "推荐理由要跟着一起给出来"
    # 能量目标还没核实这件事必须一路带到页面上，不能在中途丢掉
    assert body["target_basis"]["energy_verified"] is False
    assert "excluded_dishes" in body


def test_predictions_are_persisted_for_the_planned_dishes_only(
    as_recorder: TestClient, db_session: Session
) -> None:
    """预测结果要落库便于复盘，但只落**入选的**菜，不是整个候选池。"""
    target = today_local() + timedelta(days=1)

    body = as_recorder.post(
        f"{BASE}/generate", params={"on_date": target.isoformat(), "meal_type": "LUNCH"}
    ).json()

    db_session.expire_all()
    rows = db_session.scalars(
        select(Forecast).where(Forecast.date == target, Forecast.meal_type == MealType.LUNCH)
    ).all()

    assert len(rows) == len(body["dishes"]), "入选的每一道菜都该有份数记录"
    assert {str(row.dish_id) for row in rows} == {dish["dish_id"] for dish in body["dishes"]}
    assert all(Decimal(str(row.predicted_servings)) > 0 for row in rows)
    # 快照要能自解释：复盘时看得出这个份数是怎么来的
    assert all(row.features["model"] for row in rows)
    assert all(row.features["samples"] for row in rows)


def test_requires_login(client: TestClient) -> None:
    response = client.post(f"{BASE}/generate", params={"on_date": today_local().isoformat()})
    assert response.status_code == 401


def test_school_admin_cannot_generate_the_menu(as_school_admin: TestClient) -> None:
    """定菜单、下采购单是食堂的职责，学校管理方只看结果。"""
    response = as_school_admin.post(
        f"{BASE}/generate", params={"on_date": today_local().isoformat()}
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# 采购单本身
# ---------------------------------------------------------------------------
def test_unpriced_material_sinks_to_the_bottom(db_session: Session) -> None:
    """缺单价时如实留空，并排到最后——算不出金额的料不该占着最该先看的位置。"""
    dish_id = db_session.scalar(select(RecipeItem.dish_id).limit(1))
    assert dish_id is not None, "演示数据里应当有配方"

    unpriced = Ingredient(
        name="测试用无单价食材",
        category=IngredientCategory.CONDIMENT,
        data_source="测试构造",
        unit_price=None,
    )
    db_session.add(unpriced)
    db_session.flush()
    db_session.add(
        RecipeItem(dish_id=dish_id, ingredient_id=unpriced.id, quantity_per_serving_g=Decimal("50"))
    )
    db_session.flush()

    requirements, total_cost = forecast_service.build_purchase_list(
        db_session, servings_by_dish={dish_id: Decimal("200")}
    )

    assert requirements[-1].name == "测试用无单价食材"
    assert requirements[-1].estimated_cost is None
    assert requirements[-1].quantity == "10.000"
    assert total_cost is not None
    assert Decimal(total_cost) == sum(
        (Decimal(row.estimated_cost) for row in requirements if row.estimated_cost), Decimal("0")
    ).quantize(Decimal("0.01"))


def test_empty_plan_yields_no_purchase_list(db_session: Session) -> None:
    """没有菜就没有采购单——不要造出一张空表冒充建议。"""
    requirements, total_cost = forecast_service.build_purchase_list(db_session, servings_by_dish={})
    assert requirements == []
    assert total_cost is None

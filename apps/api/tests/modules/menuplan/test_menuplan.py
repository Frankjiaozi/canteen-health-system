"""「明日菜单与采购」的行为约定。

这个接口是三个域的**编排**：推荐选菜、预测给份数、两者相乘得到采购量。
所以用例盯的不是「算法对不对」（那两组各有自己的用例），而是三件容易出错的事：

1. **份数口径**：采购量必须等于「推荐选出的菜 × 该菜明天的预测份数」，
   不能顺手用推荐那边的份数、也不能退回「每人一份」蒙一个数；
2. **采购单的可用性**：单位是公斤、按金额从大到小排、没单价的不占前排；
3. **拿不到份数时不装**：预测不出来的菜如实标注并说明采购按什么算的。
"""

from __future__ import annotations

import itertools
from collections import defaultdict
from collections.abc import Iterator
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

import pytest
from app.db.session import get_session_factory
from app.modules.collection.models import DailyLog, DailyLogItem
from app.modules.dish.models import Dish, RecipeItem, RecipeSeasoning
from app.modules.forecast import service as forecast_service
from app.modules.forecast.models import Forecast
from app.modules.ingredient.models import Ingredient
from app.modules.menu.models import MenuDay, MenuDayItem
from app.modules.menuplan import service
from app.modules.nutrition.models import DishNutrition
from app.modules.recommendation.models import MenuSuggestion
from app.modules.seasoning.models import Seasoning
from app.shared.enums import IngredientCategory, MealType
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from tests.helpers import today_local

BASE = "/api/v1/menu-plan"
COLLECTION = "/api/v1/collection"
BOARD = "/api/v1/public/board/today"
RECOMMENDATION = "/api/v1/recommendation"


def _fresh_date() -> date:
    """种子历史之外的一天。

    同步用例会往将来写菜单日与营养结果，而**很多用例把「最新的菜单日」当成今天**
    （大屏、看板、营养计算都这么取）。挑一个固定偏移的将来日期，再在用例结束后清掉，
    就不会给别的用例下绊子。
    """
    return today_local() + timedelta(days=30)


@pytest.fixture(autouse=True)
def cleanup_beyond_seed_history() -> Iterator[None]:
    """用例结束后，把种子历史之后新建的菜单日、营养结果与份数记录删掉。"""
    cutoff = today_local()
    yield
    with get_session_factory()() as session:
        log_ids = list(session.scalars(select(DailyLog.id).where(DailyLog.date > cutoff)))
        if log_ids:
            session.execute(delete(DailyLogItem).where(DailyLogItem.daily_log_id.in_(log_ids)))
        session.execute(delete(DailyLog).where(DailyLog.date > cutoff))
        menu_ids = list(session.scalars(select(MenuDay.id).where(MenuDay.date > cutoff)))
        if menu_ids:
            session.execute(delete(MenuDayItem).where(MenuDayItem.menu_day_id.in_(menu_ids)))
        session.execute(delete(MenuDay).where(MenuDay.date > cutoff))
        session.execute(delete(DishNutrition).where(DishNutrition.date > cutoff))
        session.execute(delete(Forecast).where(Forecast.date > cutoff))
        session.execute(delete(MenuSuggestion).where(MenuSuggestion.date > cutoff))
        session.commit()


def _generate(client: TestClient, target: date) -> dict:
    response = client.post(
        f"{BASE}/generate", params={"on_date": target.isoformat(), "meal_type": "LUNCH"}
    )
    assert response.status_code == 200, response.text
    return response.json()


def _generate_meal(client: TestClient, target: date, meal: MealType) -> dict:
    response = client.post(
        f"{BASE}/generate",
        params={"on_date": target.isoformat(), "meal_type": meal.value},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _sync(client: TestClient, target: date, suggestion_id: str):
    return client.post(
        f"{BASE}/sync",
        params={
            "on_date": target.isoformat(),
            "meal_type": "LUNCH",
            "suggestion_id": suggestion_id,
        },
    )


def _fresh_range(offset: int, days: int) -> tuple[date, date]:
    """种子历史之外的一段日期。每个用例挑自己的偏移，免得互相踩。"""
    start = today_local() + timedelta(days=offset)
    return start, start + timedelta(days=days - 1)


def _batch_generate(client: TestClient, start: date, end: date):
    return client.post(
        f"{BASE}/batch/generate",
        params={"start_date": start.isoformat(), "end_date": end.isoformat(), "meal_type": "LUNCH"},
    )


def _batch_sync(client: TestClient, start: date, end: date):
    return client.post(
        f"{BASE}/batch/sync",
        params={"start_date": start.isoformat(), "end_date": end.isoformat(), "meal_type": "LUNCH"},
    )


def _dish_id(client: TestClient, name: str) -> str:
    body = client.get("/api/v1/dishes", params={"page_size": 100}).json()
    return next(item["id"] for item in body["items"] if item["name"] == name)


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
def test_breakfast_is_the_fixed_set_from_the_dish_library(
    as_recorder: TestClient, db_session: Session
) -> None:
    """早餐按固定组合供应：上哪几道菜由菜品库的标记决定，不走每日选菜。

    这条同时守住两件事：早餐每天一样（求解器不会因为目标区间不同而给出另一套），
    以及「固定」这件事在页面上讲得清楚——它没有求解，也就没有贴边约束这类理由。
    """
    staples = set(db_session.scalars(select(Dish.name).where(Dish.is_breakfast_staple.is_(True))))
    assert staples, "种子里应当有几道勾了「早餐固定供应」的菜"

    plan = _generate_meal(as_recorder, _fresh_date(), MealType.BREAKFAST)
    names = [dish["dish_name"] for dish in plan["dishes"]]

    assert set(names) == staples
    assert any("固定" in reason["text"] for reason in plan["reasons"])


def test_the_three_meals_of_a_day_do_not_share_dishes(as_recorder: TestClient) -> None:
    """同一天的早/午/晚必须是三套菜。主食允许重样，别的菜不行。

    这正是要修的那个毛病：以前早晚餐的营养目标是一个数、排除集又都空着，
    求解器拿到一模一样的输入，自然给出一模一样的菜单。
    """
    target = _fresh_date()
    breakfast = _generate_meal(as_recorder, target, MealType.BREAKFAST)
    lunch = _generate_meal(as_recorder, target, MealType.LUNCH)
    dinner = _generate_meal(as_recorder, target, MealType.DINNER)

    def names(plan: dict, *, skip_staple: bool = False) -> set[str]:
        return {
            dish["dish_name"]
            for dish in plan["dishes"]
            if not (skip_staple and dish["category_label"] == "主食")
        }

    # 主食只有米饭与馒头两道，一天两餐都排除的话根本选不出菜单
    assert names(lunch, skip_staple=True) & names(dinner, skip_staple=True) == set()
    # 早餐的菜不进午晚餐的池子，一天里不会出现两次
    assert names(breakfast) & names(lunch) == set()
    assert names(breakfast) & names(dinner) == set()
    assert names(lunch) != names(dinner)


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


def test_sync_puts_the_plan_into_the_day_for_collection_and_board(
    as_recorder: TestClient, db_session: Session
) -> None:
    """「同步至当日数据」要一次接通两处：采集页的供应菜品、公开大屏的当日菜单。

    这是交互上的一条硬要求：大屏早上就开始显示，而采集要到一天结束才录；
    靠人工在采集页重勾一遍，大屏整个白天就是空的。
    """
    target = _fresh_date()
    plan = _generate(as_recorder, target)

    synced = _sync(as_recorder, target, plan["suggestion_id"])
    assert synced.status_code == 200, synced.text
    body = synced.json()
    assert body["dish_count"] == len(plan["dishes"])
    assert body["nutrition_rows"] == len(plan["dishes"]), "每道菜都要算出单份营养，大屏才有内容"
    assert body["planned_servings_filled"] == len(plan["dishes"])

    # 每日采集：整份菜品库都列着（临时换菜有地方勾），计划里的菜已经勾好
    sheet = as_recorder.get(
        f"{COLLECTION}/logs/{target.isoformat()}", params={"meal_type": "LUNCH"}
    ).json()
    assert sheet["menu_confirmed"] is True
    assert len(sheet["dishes"]) >= 20
    planned = [row for row in sheet["dishes"] if row["is_planned"]]
    assert {row["dish_id"] for row in planned} == {dish["dish_id"] for dish in plan["dishes"]}
    assert all(row["selected"] for row in planned)
    assert all(row["planned_servings"] for row in planned)
    # 计划里的菜排在最前面，录入员一眼看到的就是「今天计划做的那几道」
    assert all(row["is_planned"] for row in sheet["dishes"][: len(planned)])
    assert "计划" in sheet["warning"]

    # 公开大屏：免登录就能看到这一天的菜单与营养
    board = as_recorder.get(BOARD, params={"on_date": target.isoformat()}).json()
    assert board["meal_label"] == "午餐"
    assert {card["name"] for card in board["dishes"]} == {
        dish["dish_name"] for dish in plan["dishes"]
    }
    assert all(len(card["nutrients"]) == 5 for card in board["dishes"])

    # 同步即采纳：历史里查得到「这一版被用上了」
    detail = as_recorder.get(f"{RECOMMENDATION}/{plan['suggestion_id']}").json()
    assert detail["status"] == "ACCEPTED"


def test_resync_replaces_the_plan_instead_of_piling_up(as_recorder: TestClient) -> None:
    """同一版菜单同步两次是幂等的；换成新一版则整份替换。"""
    target = _fresh_date()
    first = _generate(as_recorder, target)
    assert _sync(as_recorder, target, first["suggestion_id"]).status_code == 200

    assert _sync(as_recorder, target, first["suggestion_id"]).status_code == 200
    sheet = as_recorder.get(
        f"{COLLECTION}/logs/{target.isoformat()}", params={"meal_type": "LUNCH"}
    ).json()
    assert sum(1 for row in sheet["dishes"] if row["is_planned"]) == len(first["dishes"])

    second = _generate(as_recorder, target)
    assert _sync(as_recorder, target, second["suggestion_id"]).status_code == 200
    sheet = as_recorder.get(
        f"{COLLECTION}/logs/{target.isoformat()}", params={"meal_type": "LUNCH"}
    ).json()
    planned = {row["dish_id"] for row in sheet["dishes"] if row["is_planned"]}
    assert planned == {dish["dish_id"] for dish in second["dishes"]}, "菜单按最新一版整体替换"


def test_sync_refuses_to_overwrite_a_day_that_was_already_collected(
    as_recorder: TestClient, db_session: Session
) -> None:
    """已经录过采集的日子，菜单以实际供应为准——不能被计划盖掉。"""
    target = _fresh_date()
    plan = _generate(as_recorder, target)
    dish_ids = [dish["dish_id"] for dish in plan["dishes"][:2]]
    saved = as_recorder.put(
        f"{COLLECTION}/logs/{target.isoformat()}",
        json={
            "meal_type": "LUNCH",
            "diner_count": 300,
            "oil_total_g": "1000",
            "salt_total_g": "400",
            "sugar_total_g": "150",
            "leftover_weight_g": "2000",
            "note": None,
            "anomaly_flags": [],
            "dishes": [{"dish_id": dish_id, "servings_produced": "140"} for dish_id in dish_ids],
        },
    )
    assert saved.status_code == 200, saved.text

    refused = _sync(as_recorder, target, plan["suggestion_id"])
    assert refused.status_code == 422
    assert "已经录过采集" in refused.json()["message"]

    db_session.expire_all()
    sheet = as_recorder.get(
        f"{COLLECTION}/logs/{target.isoformat()}", params={"meal_type": "LUNCH"}
    ).json()
    selected = {row["dish_id"] for row in sheet["dishes"] if row["selected"]}
    assert selected == set(dish_ids), "原有菜单不该被计划覆盖"


def test_collection_keeps_the_planned_servings_for_reconciliation(
    as_recorder: TestClient,
) -> None:
    """提交实际份数之后，计划份数仍然留着——否则「计划做多少、实际做多少」事后对不上。"""
    target = _fresh_date()
    plan = _generate(as_recorder, target)
    assert _sync(as_recorder, target, plan["suggestion_id"]).status_code == 200

    dish_ids = [dish["dish_id"] for dish in plan["dishes"]]
    saved = as_recorder.put(
        f"{COLLECTION}/logs/{target.isoformat()}",
        json={
            "meal_type": "LUNCH",
            "diner_count": 300,
            "oil_total_g": "1000",
            "salt_total_g": "400",
            "sugar_total_g": "150",
            "leftover_weight_g": "2000",
            "note": None,
            "anomaly_flags": [],
            "dishes": [{"dish_id": dish_id, "servings_produced": "12"} for dish_id in dish_ids],
        },
    )
    assert saved.status_code == 200, saved.text

    sheet = as_recorder.get(
        f"{COLLECTION}/logs/{target.isoformat()}", params={"meal_type": "LUNCH"}
    ).json()
    planned_rows = [row for row in sheet["dishes"] if row["is_planned"]]
    # 提交采集之后不该再标「计划」：那一天供应的是实际做的事
    assert planned_rows == []
    recorded = [row for row in sheet["dishes"] if row["servings_produced"] == "12.00"]
    assert len(recorded) == len(dish_ids)
    assert all(row["planned_servings"] not in (None, "12.00") for row in recorded), (
        "计划份数应当保留，且与实际的 12 份不同"
    )


def test_sync_rejects_a_suggestion_from_another_day(as_recorder: TestClient) -> None:
    """把别的日期那一版菜单同步到这一天，属于张冠李戴，必须拦住。"""
    target = _fresh_date()
    plan = _generate(as_recorder, target)

    refused = _sync(as_recorder, target + timedelta(days=1), plan["suggestion_id"])
    assert refused.status_code == 422
    assert "对不上" in refused.json()["message"]


def test_servings_far_above_diner_count_is_explained() -> None:
    """人次与份数量级对不上时要能说出来。

    实测踩到的：库里某天的人次被录成 180，而份数按历史预测是 300~900 份，
    人均油盐糖被放大到任何菜单都超上限——求解器只会说「约束互相冲突」，
    看的人完全不知道问题出在人次上。这条补充说明只在**排不出来之后**加上，
    不当事先的门槛：量级偏大但仍然排得出来的情况是有的（求解器可以挑低盐的菜）。
    """
    note = service.servings_mismatch_note(
        [Decimal("909.67"), Decimal("471.01"), Decimal("316.56")], diners=180
    )
    assert note is not None
    assert "就餐人次" in note
    assert "预测份数" in note
    assert "180" in note

    # 量级正常时不加这句话，免得把原因说岔
    assert (
        service.servings_mismatch_note(
            [Decimal("909.67"), Decimal("471.01"), Decimal("316.56")], diners=885
        )
        is None
    )


def test_unsatisfiable_menu_comes_back_as_a_readable_error(as_recorder: TestClient) -> None:
    """排不出菜单时要说明卡在哪条约束上（422），不能冒成 500——
    界面上只剩一句「服务器内部错误」的话，求解器算出来的原因就白算了。
    """
    target = _fresh_date()

    response = as_recorder.post(
        f"{BASE}/generate",
        params={"on_date": target.isoformat(), "meal_type": "LUNCH", "diner_count": 5},
    )

    assert response.status_code == 422, response.text
    message = response.json()["message"]
    assert any(word in message for word in ("预算", "上限", "无解")), message


def test_batch_generates_every_day_and_does_not_alternate_two_menus(
    as_recorder: TestClient,
) -> None:
    """批量排菜单的关键不是「生成了」，而是**排出来的菜单真的是轮换**。

    只排除「昨天」那几道时，求解器每天都会从剩下的菜里挑出同一个最优解，
    12 天会排成「A、B、A、B」；这条用例就是盯着这件事的。
    """
    start, end = _fresh_range(30, 6)

    response = _batch_generate(as_recorder, start, end)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["generated"] == 6
    assert body["failed"] == 0 and body["skipped"] == 0
    rows = body["rows"]
    assert [row["date"] for row in rows] == [
        (start + timedelta(days=offset)).isoformat() for offset in range(6)
    ]
    assert all(row["dish_count"] >= 4 for row in rows)
    assert all(row["suggestion_id"] for row in rows)
    assert all(row["cost_per_person"] for row in rows)

    menus = [frozenset(row["dish_names"]) for row in rows]
    # ① 相邻两天不重样（这是需求里那条硬约束）
    for earlier, later in itertools.pairwise(menus):
        assert not (earlier & later), "同一道菜不该连续两天出现"
    # ② 整段不要只有两三种组合在循环
    assert len(set(menus)) >= 5, f"6 天只排出了 {len(set(menus))} 种组合，等于没轮换"


def test_batch_skips_days_that_already_have_a_collection(
    as_recorder: TestClient,
) -> None:
    """已经录过采集的日子不排——排了也盖不上去。"""
    start, end = _fresh_range(40, 3)
    collected_day = start + timedelta(days=1)
    rice = _dish_id(as_recorder, "米饭")
    saved = as_recorder.put(
        f"{COLLECTION}/logs/{collected_day.isoformat()}",
        json={
            "meal_type": "LUNCH",
            "diner_count": 900,
            "oil_total_g": "1000",
            "salt_total_g": "400",
            "sugar_total_g": "150",
            "leftover_weight_g": "2000",
            "note": None,
            "anomaly_flags": [],
            "dishes": [{"dish_id": rice, "servings_produced": "150"}],
        },
    )
    assert saved.status_code == 200, saved.text

    body = _batch_generate(as_recorder, start, end).json()

    by_status = {row["date"]: row for row in body["rows"]}
    assert by_status[collected_day.isoformat()]["status"] == "SKIPPED"
    assert "已经录过采集" in by_status[collected_day.isoformat()]["reason"]
    assert body["generated"] == 2


def test_batch_sync_imports_every_generated_day(as_recorder: TestClient) -> None:
    """一键导入：这几天的采集页与公开大屏都要就位。"""
    start, end = _fresh_range(50, 3)
    assert _batch_generate(as_recorder, start, end).status_code == 200

    response = _batch_sync(as_recorder, start, end)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["imported"] == 3
    assert body["failed"] == 0
    assert all(row["nutrition_rows"] > 0 for row in body["rows"])

    planned_counts: list[int] = []
    for offset in range(3):
        day = start + timedelta(days=offset)
        sheet = as_recorder.get(
            f"{COLLECTION}/logs/{day.isoformat()}", params={"meal_type": "LUNCH"}
        ).json()
        assert sheet["menu_confirmed"] is True
        planned = [row for row in sheet["dishes"] if row["is_planned"]]
        assert planned, f"{day} 的采集页没有按计划勾好"
        planned_counts.append(len(planned))

        board = as_recorder.get(BOARD, params={"on_date": day.isoformat()}).json()
        assert {card["name"] for card in board["dishes"]} == {row["name"] for row in planned}

    # 再导入一次是幂等的：不重复、不报错
    again = _batch_sync(as_recorder, start, end).json()
    assert again["imported"] == 3
    for offset in range(3):
        day = start + timedelta(days=offset)
        sheet = as_recorder.get(
            f"{COLLECTION}/logs/{day.isoformat()}", params={"meal_type": "LUNCH"}
        ).json()
        planned = [row for row in sheet["dishes"] if row["is_planned"]]
        assert len(planned) == planned_counts[offset], "重复导入不该把菜单越叠越多"


def test_batch_sync_reports_days_without_a_menu(as_recorder: TestClient) -> None:
    """没生成过的日子要说明白，而不是静默跳过。"""
    start, end = _fresh_range(60, 2)
    assert _batch_generate(as_recorder, start, start).status_code == 200

    body = _batch_sync(as_recorder, start, end).json()

    by_status = {row["date"]: row for row in body["rows"]}
    assert by_status[start.isoformat()]["status"] == "IMPORTED"
    later = by_status[(start + timedelta(days=1)).isoformat()]
    assert later["status"] == "SKIPPED"
    assert "还没有生成过菜单" in later["reason"]


def test_batch_rejects_a_bad_range(as_recorder: TestClient) -> None:
    start, end = _fresh_range(70, 2)

    reversed_range = _batch_generate(as_recorder, end, start)
    assert reversed_range.status_code == 422
    assert "结束日期不能早于" in reversed_range.json()["message"]

    too_long = _batch_generate(as_recorder, start, start + timedelta(days=40))
    assert too_long.status_code == 422
    assert "最多排" in too_long.json()["message"]


def test_batch_requires_login(client: TestClient) -> None:
    start, end = _fresh_range(80, 2)
    params = {"start_date": start.isoformat(), "end_date": end.isoformat(), "meal_type": "LUNCH"}

    assert client.post(f"{BASE}/batch/generate", params=params).status_code == 401
    assert client.post(f"{BASE}/batch/sync", params=params).status_code == 401


def test_school_admin_cannot_run_the_batch(as_school_admin: TestClient) -> None:
    """批量排菜单与导入都是「定菜单、下采购单」的活，学校管理方不参与。"""
    start, end = _fresh_range(82, 2)
    params = {"start_date": start.isoformat(), "end_date": end.isoformat(), "meal_type": "LUNCH"}

    assert as_school_admin.post(f"{BASE}/batch/generate", params=params).status_code == 403
    assert as_school_admin.post(f"{BASE}/batch/sync", params=params).status_code == 403


def test_sync_requires_login(client: TestClient) -> None:
    response = client.post(
        f"{BASE}/sync",
        params={
            "on_date": today_local().isoformat(),
            "meal_type": "LUNCH",
            "suggestion_id": "00000000-0000-0000-0000-000000000000",
        },
    )
    assert response.status_code == 401


def test_school_admin_cannot_sync_to_the_day(as_school_admin: TestClient) -> None:
    response = as_school_admin.post(
        f"{BASE}/sync",
        params={
            "on_date": today_local().isoformat(),
            "meal_type": "LUNCH",
            "suggestion_id": "00000000-0000-0000-0000-000000000000",
        },
    )
    assert response.status_code == 403


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

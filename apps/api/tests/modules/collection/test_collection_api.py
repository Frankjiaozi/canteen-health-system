"""每日采集接口的行为约定。

采集是整条链路的起点，所以这里盯的是两件事：**录入的数据真的落库并参与了营养计算**，
以及**异常标记不会被系统与人工互相覆盖**。

用例刻意挑在种子历史之外的日子（最新菜单日再加 30 天）。采集会改动当天的每日记录，
而种子历史既是校准拟合的输入、又是看板与回测的样本，动它等于给别的用例下绊子。
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from app.core.config import get_settings
from app.db.session import get_session_factory
from app.modules.collection.models import DailyLog, DailyLogItem
from app.modules.dish.models import Dish, RecipeSeasoning
from app.modules.menu.models import MenuDay, MenuDayItem
from app.modules.nutrition.models import CalibrationFactor, DishNutrition
from app.modules.seasoning.models import Seasoning
from app.shared.enums import (
    AnomalyFlag,
    MealType,
    NutrientCaliber,
    NutritionValueType,
    SeasoningCategory,
)
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from tests.helpers import today_local

BASE = "/api/v1/collection"
BOARD = "/api/v1/public/board/today"
CLOSURE = "/api/v1/calibration/daily-closure"


def _fresh_date(db_session: Session) -> date:
    """种子历史之外的一天。

    用"今天 + 30 天"而不是"最新菜单日 + 30 天"：开发库里可能留着端到端用例造出来的
    未来日期，从最大值往上加会落到更远的地方，清理边界的判断也就跟着漂了。
    """
    return today_local() + timedelta(days=30)


@pytest.fixture(autouse=True)
def cleanup_beyond_seed_history() -> Iterator[None]:
    """用例结束后，把种子历史之后新建的采集相关行全部删掉。

    这些用例会在最新菜单日之后再造一段采集历史，而**很多用例把"最新的菜单日"当成
    今天**（大屏、看板、营养计算都这么取）。不清掉的话，下一个用例算的就是我造的那一天，
    报错信息还会指向完全无关的地方。种子历史以当天为界，因此"晚于今天"就是安全的判据。
    """
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
        session.execute(delete(CalibrationFactor).where(CalibrationFactor.date > cutoff))
        session.commit()


def _dish_ids(db_session: Session, *names: str) -> list[str]:
    return [
        str(value)
        for value in db_session.scalars(select(Dish.id).where(Dish.name.in_(names))).all()
    ]


def _payload(dish_ids: list[str], **overrides: object) -> dict:
    body: dict = {
        "meal_type": "LUNCH",
        "diner_count": 260,
        "oil_total_g": "1200",
        "salt_total_g": "420",
        "sugar_total_g": "180",
        "leftover_weight_g": "3200",
        "note": "用例录入",
        "anomaly_flags": [],
        "dishes": [
            {
                "dish_id": dish_id,
                "servings_produced": "140",
                "leftover_ratio": "0.05",
                "leftover_weight_g": "600",
            }
            for dish_id in dish_ids
        ],
    }
    body.update(overrides)
    return body


def _seasoning_per_serving(session: Session, dish_ids: list[str]) -> dict[str, dict[str, Decimal]]:
    """这几道菜**单份**的调料用量（克），按类别。"""
    rows = session.execute(
        select(RecipeSeasoning.dish_id, Seasoning.category, RecipeSeasoning.quantity_per_serving_g)
        .join(Seasoning, Seasoning.id == RecipeSeasoning.seasoning_id)
        .where(RecipeSeasoning.dish_id.in_(dish_ids))
    ).all()
    per_serving: dict[str, dict[str, Decimal]] = {}
    for dish_id, category, quantity in rows:
        per_serving.setdefault(str(dish_id), {})[category.value] = quantity
    return per_serving


def _history_servings(index: int, offset: int) -> Decimal:
    """逐日变化的出餐份数。

    刻意让每道菜的份数独立变动：如果所有菜每天按同一比例缩放，各烹饪方式的推算量
    就完全共线，方程解不出各自的偏置（只能靠岭项硬压一个答案），那测的就不是真实的估计能力了。
    """
    return Decimal(80 + ((offset + index * 3) % 7) * 10)


def _prepare_history(
    session: Session, *, target: date, dish_ids: list[str], days: int = 21
) -> None:
    """给目标日之前造一段"用量与配方吻合"的合成采集历史，让校准拟合有数据可用。

    为什么不直接用种子历史：那样就得改种子那天的每日记录，而它既是校准的输入、
    又是看板与回测的样本，动它会给别的用例下绊子。合成数据落在种子历史之外，
    测试收尾时会整片删掉。
    """
    per_serving = _seasoning_per_serving(session, dish_ids)
    submitted_at = datetime.now(get_settings().timezone)
    for offset in range(days, 0, -1):
        day = target - timedelta(days=offset)
        totals = {category.value: Decimal("0") for category in SeasoningCategory}
        servings = {
            dish_id: _history_servings(index, offset) for index, dish_id in enumerate(dish_ids)
        }
        for dish_id, by_category in per_serving.items():
            for code, amount in by_category.items():
                totals[code] += amount * servings[dish_id]
        log = DailyLog(
            date=day,
            meal_type=MealType.LUNCH,
            diner_count=200,
            oil_total_g=totals[SeasoningCategory.EDIBLE_OIL.value],
            salt_total_g=totals[SeasoningCategory.SALT.value],
            sugar_total_g=totals[SeasoningCategory.SUGAR.value],
            leftover_weight_g=Decimal("1000"),
            anomaly_flags=[],
            submitted_at=submitted_at,
        )
        session.add(log)
        session.flush()
        for dish_id in dish_ids:
            session.add(
                DailyLogItem(
                    daily_log_id=log.id,
                    dish_id=UUID(dish_id),
                    servings_produced=servings[dish_id],
                    leftover_ratio=Decimal("0.05"),
                )
            )
        session.flush()
    session.commit()
    return per_serving


def _implied_total(
    per_serving: dict[str, dict[str, Decimal]],
    servings: Decimal,
    category: SeasoningCategory,
) -> Decimal:
    """这几道菜在给定份数下按配方推算的某类调料总量。"""
    return (
        sum(by_category.get(category.value, Decimal("0")) for by_category in per_serving.values())
        * servings
    )


def _consistent_payload(
    ids: list[str],
    per_serving: dict[str, dict[str, Decimal]],
    *,
    oil_multiplier: Decimal,
    **overrides: object,
) -> dict:
    """按菜单推算的用量造一份采集单，油可以乘以一个倍数用来制造偏差。

    盐和糖必须跟着推算量走：写死一个数会让校验项把「填的数与菜单对不上」如实标出来，
    那样测到的就不是我想验的那件事了。
    """
    servings = Decimal("140")
    return _payload(
        ids,
        oil_total_g=str(
            _implied_total(per_serving, servings, SeasoningCategory.EDIBLE_OIL) * oil_multiplier
        ),
        salt_total_g=str(_implied_total(per_serving, servings, SeasoningCategory.SALT)),
        sugar_total_g=str(_implied_total(per_serving, servings, SeasoningCategory.SUGAR)),
        **overrides,
    )


def test_sheet_offers_the_dish_pool_before_any_menu_exists(
    as_recorder: TestClient, db_session: Session
) -> None:
    """当天还没排菜单时要能直接勾菜，否则第一次录入无从下手。"""
    target = _fresh_date(db_session)

    sheet = as_recorder.get(
        f"{BASE}/logs/{target.isoformat()}", params={"meal_type": "LUNCH"}
    ).json()

    assert sheet["saved"] is False
    assert sheet["menu_confirmed"] is False
    assert len(sheet["dishes"]) >= 20, "应当把整份菜品库列出来供勾选"
    assert all(row["selected"] is False for row in sheet["dishes"])
    assert sheet["warning"]


def test_save_confirms_menu_and_recomputes_nutrition(
    as_recorder: TestClient, db_session: Session
) -> None:
    """保存即为确认菜单，并立刻重算当餐营养——闭环就是在这里接上的。"""
    target = _fresh_date(db_session)
    ids = _dish_ids(db_session, "土豆炖牛肉", "米饭")
    assert len(ids) == 2

    saved = as_recorder.put(f"{BASE}/logs/{target.isoformat()}", json=_payload(ids))

    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["dish_count"] == 2
    assert body["nutrition_rows"] > 0, "保存后应当自动重算营养结果"

    sheet = as_recorder.get(
        f"{BASE}/logs/{target.isoformat()}", params={"meal_type": "LUNCH"}
    ).json()
    assert sheet["saved"] is True
    assert sheet["menu_confirmed"] is True
    assert sheet["diner_count"] == 260
    selected = {row["dish_id"] for row in sheet["dishes"] if row["selected"]}
    assert selected == set(ids), "菜单里应当只有勾选的这两道菜"
    assert all(row["servings_produced"] == "140.00" for row in sheet["dishes"] if row["selected"])

    db_session.expire_all()
    item_rows = db_session.scalars(
        select(DailyLogItem)
        .join(DailyLog, DailyLog.id == DailyLogItem.daily_log_id)
        .where(DailyLog.date == target, DailyLog.meal_type == MealType.LUNCH)
    ).all()
    assert len(item_rows) == 2
    assert all(row.recipe_snapshot is not None for row in item_rows)
    assert all(row.recipe_snapshot["recipe_version"] >= 1 for row in item_rows)

    rows = db_session.scalar(
        select(func.count())
        .select_from(DishNutrition)
        .where(
            DishNutrition.date == target,
            DishNutrition.caliber == NutrientCaliber.PER_SERVING,
            DishNutrition.value_type == NutritionValueType.THEORETICAL,
        )
    )
    assert rows == 2, "两道菜都应当有单份理论值"


def test_saved_collection_shows_up_on_the_public_board(
    as_recorder: TestClient, client: TestClient, db_session: Session
) -> None:
    """录入之后大屏就看得见——这是需求里那条闭环的验收点。"""
    target = _fresh_date(db_session)
    ids = _dish_ids(db_session, "醋溜白菜", "米饭")

    as_recorder.put(f"{BASE}/logs/{target.isoformat()}", json=_payload(ids))

    # 大屏是免登录接口，这里用未登录的客户端取，顺带验证它确实不要求身份
    board = client.get(BOARD, params={"on_date": target.isoformat()}).json()

    assert {card["name"] for card in board["dishes"]} == {"醋溜白菜", "米饭"}
    assert all(card["nutrients"] for card in board["dishes"])


def test_diner_count_and_seasoning_totals_reach_the_database(
    as_recorder: TestClient, db_session: Session
) -> None:
    target = _fresh_date(db_session)
    ids = _dish_ids(db_session, "米饭")

    as_recorder.put(
        f"{BASE}/logs/{target.isoformat()}",
        json=_payload(ids, oil_total_g="1234.56", salt_total_g="321.5", sugar_total_g="77"),
    )

    db_session.expire_all()
    log = db_session.scalar(
        select(DailyLog).where(DailyLog.date == target, DailyLog.meal_type == MealType.LUNCH)
    )
    assert log is not None
    assert log.oil_total_g == Decimal("1234.56")
    assert log.salt_total_g == Decimal("321.50")
    assert log.sugar_total_g == Decimal("77.00")
    assert log.submitted_at is not None, "保存应当记录提交时间"


def test_missing_seasoning_is_stored_as_null(as_recorder: TestClient, db_session: Session) -> None:
    """空值不能被悄悄写成 0：未测量和明确测到零是两种业务事实。"""
    target = _fresh_date(db_session)
    ids = _dish_ids(db_session, "米饭")

    response = as_recorder.put(
        f"{BASE}/logs/{target.isoformat()}",
        json=_payload(
            ids,
            oil_total_g=None,
            salt_total_g=None,
            sugar_total_g=None,
        ),
    )
    assert response.status_code == 200, response.text

    db_session.expire_all()
    log = db_session.scalar(
        select(DailyLog).where(DailyLog.date == target, DailyLog.meal_type == MealType.LUNCH)
    )
    assert log is not None
    assert log.oil_total_g is None
    assert log.salt_total_g is None
    assert log.sugar_total_g is None

    sheet = as_recorder.get(
        f"{BASE}/logs/{target.isoformat()}", params={"meal_type": "LUNCH"}
    ).json()
    assert sheet["oil_total_g"] is None
    assert sheet["salt_total_g"] is None
    assert sheet["sugar_total_g"] is None


def test_zero_diner_count_is_rejected(as_recorder: TestClient, db_session: Session) -> None:
    target = _fresh_date(db_session)
    ids = _dish_ids(db_session, "米饭")

    response = as_recorder.put(
        f"{BASE}/logs/{target.isoformat()}",
        json=_payload(ids, diner_count=0),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_empty_dish_list_is_rejected(as_recorder: TestClient, db_session: Session) -> None:
    target = _fresh_date(db_session)

    response = as_recorder.put(f"{BASE}/logs/{target.isoformat()}", json=_payload([]))

    assert response.status_code == 422
    assert response.json()["code"] == "business_rule_violated"
    assert "勾选" in response.json()["message"]


def test_duplicate_dish_is_rejected(as_recorder: TestClient, db_session: Session) -> None:
    target = _fresh_date(db_session)
    ids = _dish_ids(db_session, "米饭")

    response = as_recorder.put(f"{BASE}/logs/{target.isoformat()}", json=_payload([ids[0], ids[0]]))

    assert response.status_code == 422
    assert "只能出现一次" in response.json()["message"]


def test_manual_anomaly_flags_round_trip(as_recorder: TestClient, db_session: Session) -> None:
    target = _fresh_date(db_session)
    ids = _dish_ids(db_session, "米饭")

    as_recorder.put(
        f"{BASE}/logs/{target.isoformat()}",
        json=_payload(ids, anomaly_flags=["RECEPTION", "EQUIPMENT_FAILURE"]),
    )
    sheet = as_recorder.get(
        f"{BASE}/logs/{target.isoformat()}", params={"meal_type": "LUNCH"}
    ).json()

    flags = {row["value"]: row for row in sheet["anomaly_flags"]}
    assert set(flags) == {"RECEPTION", "EQUIPMENT_FAILURE"}
    assert flags["RECEPTION"]["label"] == "临时接待"
    assert flags["RECEPTION"]["system"] is False


def test_calibration_residual_is_written_back_and_cleared(
    as_recorder: TestClient, db_session: Session
) -> None:
    """校准残差要回写到异常标记上；改对数据后重跑，标记自动撤掉。

    这一条把「校准的校验结论」和「预测用不用这天」串起来：用量对不上的日子
    不适合进预测的历史序列，但它的数据仍然保留，等录入员改对之后标记会消失。
    """
    # 放到种子历史窗口之外，确保拟合样本只来自本用例构造的匹配历史。
    target = _fresh_date(db_session) + timedelta(days=60)
    ids = _dish_ids(db_session, "土豆炖牛肉", "醋溜白菜")
    assert len(ids) == 2
    per_serving = _prepare_history(db_session, target=target, dish_ids=ids)

    # 历史里每天的用量都跟配方吻合，所以拟合出的系数接近 1；
    # 目标这天却填了十倍的油，偏差必然超阈值
    as_recorder.put(
        f"{BASE}/logs/{target.isoformat()}",
        json=_consistent_payload(ids, per_serving, oil_multiplier=Decimal("10")),
    )
    body = as_recorder.post(
        CLOSURE, params={"on_date": target.isoformat(), "meal_type": "LUNCH"}
    ).json()

    # 糖只有一种烹饪方式在用，退化成整餐比值是对的；油与盐必须按方法解出来
    fallback = body["window"]["fallback_reason"] or ""
    assert "食用油" not in fallback and "食盐" not in fallback, fallback
    oil_check = next(row for row in body["checks"] if row["code"] == "EDIBLE_OIL")
    assert oil_check["status"] == "warn"

    db_session.expire_all()
    log = db_session.scalar(
        select(DailyLog).where(DailyLog.date == target, DailyLog.meal_type == MealType.LUNCH)
    )
    assert log is not None
    assert AnomalyFlag.CALIBRATION_RESIDUAL.value in log.anomaly_flags

    # 改回按配方该用的量，再跑一次：
    # 这一次拟合的输入里不再有离群值，系数回到 1 附近，偏差归零
    as_recorder.put(
        f"{BASE}/logs/{target.isoformat()}",
        json=_consistent_payload(ids, per_serving, oil_multiplier=Decimal("1")),
    )
    body = as_recorder.post(
        CLOSURE, params={"on_date": target.isoformat(), "meal_type": "LUNCH"}
    ).json()

    assert all(row["status"] == "ok" for row in body["checks"]), body["checks"]
    db_session.expire_all()
    refreshed = db_session.scalar(
        select(DailyLog).where(DailyLog.date == target, DailyLog.meal_type == MealType.LUNCH)
    )
    assert refreshed is not None
    assert AnomalyFlag.CALIBRATION_RESIDUAL.value not in refreshed.anomaly_flags


def test_resaving_keeps_the_system_flag_and_refreshes_manual_ones(
    as_recorder: TestClient, db_session: Session
) -> None:
    """人工勾选的标记以本次提交为准，系统回写的标记必须原样留住。"""
    target = _fresh_date(db_session)
    ids = _dish_ids(db_session, "土豆炖牛肉", "醋溜白菜")
    per_serving = _prepare_history(db_session, target=target, dish_ids=ids)

    as_recorder.put(
        f"{BASE}/logs/{target.isoformat()}",
        json=_consistent_payload(ids, per_serving, oil_multiplier=Decimal("10")),
    )
    as_recorder.post(CLOSURE, params={"on_date": target.isoformat(), "meal_type": "LUNCH"})

    # 第二次提交：人工标记换成「菜品停供」，系统标记不该被这次覆盖冲掉
    as_recorder.put(
        f"{BASE}/logs/{target.isoformat()}",
        json=_consistent_payload(
            ids,
            per_serving,
            oil_multiplier=Decimal("10"),
            anomaly_flags=["SUSPENDED"],
        ),
    )

    db_session.expire_all()
    log = db_session.scalar(
        select(DailyLog).where(DailyLog.date == target, DailyLog.meal_type == MealType.LUNCH)
    )
    assert log is not None
    assert set(log.anomaly_flags) == {
        AnomalyFlag.SUSPENDED.value,
        AnomalyFlag.CALIBRATION_RESIDUAL.value,
    }


def test_list_reports_dish_count_and_waste_ratio(
    as_recorder: TestClient, db_session: Session
) -> None:
    target = _fresh_date(db_session)
    ids = _dish_ids(db_session, "米饭", "醋溜白菜")
    as_recorder.put(f"{BASE}/logs/{target.isoformat()}", json=_payload(ids))

    page = as_recorder.get(
        f"{BASE}/logs",
        params={"start": target.isoformat(), "end": target.isoformat()},
    ).json()

    assert page["total"] == 1
    row = page["items"][0]
    assert row["date"] == target.isoformat()
    assert row["dish_count"] == 2
    assert row["meal_type_label"] == "午餐"
    assert row["submitted_by_name"], "列表要能看出是谁录的"
    assert Decimal(row["waste_ratio"]) > 0


def test_collection_requires_login(client: TestClient, db_session: Session) -> None:
    target = _fresh_date(db_session)

    assert client.get(f"{BASE}/logs").status_code == 401
    assert client.get(f"{BASE}/logs/{target.isoformat()}").status_code == 401
    assert client.put(f"{BASE}/logs/{target.isoformat()}", json=_payload([])).status_code == 401


def test_school_admin_can_read_but_not_write(
    as_school_admin: TestClient, db_session: Session
) -> None:
    """学校管理方是只读的观察者：能看采集记录，不能替食堂录。"""
    target = _fresh_date(db_session)

    assert as_school_admin.get(f"{BASE}/logs").status_code == 200
    assert as_school_admin.get(f"{BASE}/logs/{target.isoformat()}").status_code == 200

    response = as_school_admin.put(f"{BASE}/logs/{target.isoformat()}", json=_payload([]))
    assert response.status_code == 403

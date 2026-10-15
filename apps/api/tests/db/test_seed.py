"""种子数据的幂等性与完整性。

这些用例会写开发库，但种子脚本本身是幂等的（按确定性 UUID 覆盖），
因此重复执行不会造成数据漂移。
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from uuid import UUID

from app.db.seed import (
    DEMO_DATA_SOURCE,
    HISTORY_DAYS,
    NUTRITION_REFERENCE_PATH,
    PLATFORM_DATA_SOURCE,
    _stable_id,
    run,
)
from app.db.session import get_session_factory
from app.modules.collection.models import DailyLog, DailyLogItem
from app.modules.dish.models import Dish, RecipeItem
from app.modules.ingredient.models import Ingredient
from app.modules.menu.models import MenuDay, MenuDayItem
from app.modules.nutrition.models import NutritionStandard
from app.modules.seasoning.models import Seasoning
from app.shared.enums import MealType
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tests.helpers import today_local


def _run_seed() -> dict[str, dict[str, int]]:
    with get_session_factory()() as session:
        return run(session).counts


def test_seed_is_idempotent() -> None:
    """连跑两次，第二次不得产生任何新增或更新。"""
    _run_seed()
    second = _run_seed()

    assert second, "种子脚本应当报告各实体的写入统计"
    for entity, bucket in second.items():
        assert bucket["created"] == 0, f"{entity} 在重复执行时被重复创建"
        assert bucket["updated"] == 0, f"{entity} 在重复执行时产生了无意义的更新"
        assert bucket["unchanged"] > 0, f"{entity} 未参与比对"


def test_seed_covers_required_demo_scope(db_session: Session) -> None:
    """验收要求：不少于 20 道菜覆盖一个完整轮换。"""
    # 只数种子脚本写入的食材：连同接口测试造的数据一起数会让断言依赖执行顺序
    seeded_ingredients = db_session.scalar(
        select(func.count())
        .select_from(Ingredient)
        .where(Ingredient.data_source == PLATFORM_DATA_SOURCE)
    )
    assert seeded_ingredients == 30
    assert db_session.scalar(select(func.count()).select_from(Dish)) >= 20
    assert db_session.scalar(select(func.count()).select_from(NutritionStandard)) == 4
    # 8 周历史 × 三餐：同星期移动平均的每个星期几有 8 个样本，回测才有意义。
    # 按餐次分别数，而不是数总数：总数对得上但三餐少了一餐，是「大屏上只有午餐」
    # 这类问题最典型的伪装。
    # 以当天为界：开发库里可能留着端到端用例造的未来日期的菜单与采集记录，
    # 它们不属于种子历史，也不该让这条断言跟着变
    today = today_local()
    for meal_type in (MealType.BREAKFAST, MealType.LUNCH, MealType.DINNER):
        assert (
            db_session.scalar(
                select(func.count())
                .select_from(MenuDay)
                .where(MenuDay.date <= today, MenuDay.meal_type == meal_type)
            )
            == HISTORY_DAYS
        ), f"{meal_type.label}的菜单日数量不对"
        assert (
            db_session.scalar(
                select(func.count())
                .select_from(DailyLog)
                .where(DailyLog.date <= today, DailyLog.meal_type == meal_type)
            )
            == HISTORY_DAYS
        ), f"{meal_type.label}的采集记录数量不对"


def test_seeded_nutrition_matches_the_reference_snapshot(db_session: Session) -> None:
    """库里写进去的数值必须逐条等于快照。

    快照（``nutrition_reference.json``）才是营养数据的唯一来源，
    seed.py 只负责把它落到库上。谁要是绕过快照在代码里手写一个数字，
    这条用例就会红——「任何营养数据都能点开看到来源与版本」靠它守着。
    """

    reference = json.loads(NUTRITION_REFERENCE_PATH.read_text(encoding="utf-8"))["items"]
    assert reference, "参照快照不能是空的"

    for key, record in reference.items():
        row = db_session.get(Ingredient, _stable_id("ingredient", key)) or db_session.get(
            Seasoning, _stable_id("seasoning", key)
        )
        assert row is not None, f"快照里有「{key}」，库里却找不到"
        assert row.energy_kcal == Decimal(record["energy_kcal"]), f"{key} 的能量与快照不一致"
        assert row.protein_g == Decimal(record["protein_g"]), f"{key} 的蛋白质与快照不一致"
        assert row.fat_g == Decimal(record["fat_g"]), f"{key} 的脂肪与快照不一致"
        assert row.carb_g == Decimal(record["carb_g"]), f"{key} 的碳水与快照不一致"
        assert row.sodium_mg == Decimal(record["sodium_mg"]), f"{key} 的钠与快照不一致"

        assert row.data_source == PLATFORM_DATA_SOURCE
        assert row.source_version == f"{record['entry_name']} · 条目 {record['food_id']}"
        # 备注里要留下原始 kJ 与查询日期，换算过程才可复算
        assert row.note is not None
        assert f"{record['energy_kj']} kJ" in row.note
        assert record["energy_kj"] != "" and row.note.count("查询日期") == 1


def test_edible_ratio_comes_from_the_platform(db_session: Session) -> None:
    """可食部比例也要跟平台一致——它直接决定采购成本，不能各写各的。"""

    reference = json.loads(NUTRITION_REFERENCE_PATH.read_text(encoding="utf-8"))["items"]
    for key, record in reference.items():
        ingredient = db_session.get(Ingredient, _stable_id("ingredient", key))
        if ingredient is None:
            continue  # 调味料没有可食部这一列
        assert ingredient.edible_ratio == Decimal(record["edible_ratio"]), (
            f"{key} 的可食部比例与平台不一致"
        )


def test_item_without_a_platform_entry_stays_marked_unverified(db_session: Session) -> None:
    """平台没有的条目（蚝油）要如实标着待核对，不许冒充权威出处。"""

    oyster_sauce = db_session.scalar(select(Seasoning).where(Seasoning.name == "蚝油"))

    assert oyster_sauce is not None
    assert oyster_sauce.data_source == DEMO_DATA_SOURCE
    assert oyster_sauce.source_version is None or oyster_sauce.source_version == "未核对"
    assert oyster_sauce.note is not None and "平台无对应条目" in oyster_sauce.note


def test_every_dish_has_at_least_one_recipe_item(db_session: Session) -> None:
    """**上过菜单**的菜品必须有配方。

    不要求「所有菜品都有配方」：刚建好、还没排进菜单的菜品本来就允许没有配方
    （界面上会提示）。但一旦排进菜单，没有配方就算不出营养，属于必须拦住的缺陷。
    """
    served = set(db_session.scalars(select(MenuDayItem.dish_id).distinct()))
    with_recipe = set(db_session.scalars(select(RecipeItem.dish_id).distinct()))

    assert served
    assert served - with_recipe == set(), "存在已上菜单但没有配方明细的菜品"


def test_recipe_items_reference_existing_ingredients(db_session: Session) -> None:
    ingredient_ids = set(db_session.scalars(select(Ingredient.id)))
    referenced = set(db_session.scalars(select(RecipeItem.ingredient_id).distinct()))

    assert referenced
    assert referenced <= ingredient_ids, "配方引用了不存在的食材"


def test_history_links_menu_items_and_daily_items(db_session: Session) -> None:
    """菜单日与每日记录的明细必须对得上，否则闭环不完整。

    对得上的口径分两种日子，因为「同步至当日数据」之后菜单日会**先于**采集出现：

    - **已经过去的日子**：既有菜单日也有采集记录，两者的菜品必须完全一致
      （采集提交时按实际供应整份覆盖菜单）；
    - **将来/还没采集的日子**：允许只有菜单日没有采集记录——那正是「菜单已排好、
      还没到录入的时候」，次日采集页要靠它把供应菜品勾好。
    """
    menu_by_date: dict[date, set[UUID]] = {}
    for day, dish_id in db_session.execute(
        select(MenuDay.date, MenuDayItem.dish_id).join(
            MenuDayItem, MenuDayItem.menu_day_id == MenuDay.id
        )
    ):
        menu_by_date.setdefault(day, set()).add(dish_id)

    log_by_date: dict[date, set[UUID]] = {}
    for day, dish_id in db_session.execute(
        select(DailyLog.date, DailyLogItem.dish_id).join(
            DailyLogItem, DailyLogItem.daily_log_id == DailyLog.id
        )
    ):
        log_by_date.setdefault(day, set()).add(dish_id)

    assert menu_by_date
    missing_menu = set(log_by_date) - set(menu_by_date)
    assert not missing_menu, f"这些日子有采集记录却没有菜单日：{sorted(missing_menu)}"

    today = today_local()
    for day, dishes in log_by_date.items():
        assert menu_by_date[day] == dishes, f"{day} 的菜单与采集记录不一致"
    uncollected = {day for day in menu_by_date if day <= today} - set(log_by_date)
    assert not uncollected, f"已过去的日子只有菜单没有采集记录：{sorted(uncollected)}"


def test_submitted_logs_record_who_and_when(db_session: Session) -> None:
    logs = list(db_session.scalars(select(DailyLog)))

    assert logs
    for log in logs:
        assert log.submitted_by is not None, f"{log.date} 缺少提交人"
        assert log.submitted_at is not None, f"{log.date} 缺少提交时间"

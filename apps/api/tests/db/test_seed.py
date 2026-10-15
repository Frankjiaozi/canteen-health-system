"""种子数据的幂等性与完整性。

这些用例会写开发库，但种子脚本本身是幂等的（按确定性 UUID 覆盖），
因此重复执行不会造成数据漂移。
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from app.db.seed import DEMO_DATA_SOURCE, HISTORY_DAYS, run
from app.db.session import get_session_factory
from app.modules.collection.models import DailyLog, DailyLogItem
from app.modules.dish.models import Dish, RecipeItem
from app.modules.ingredient.models import Ingredient
from app.modules.menu.models import MenuDay, MenuDayItem
from app.modules.nutrition.models import NutritionStandard
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
        .where(Ingredient.data_source == DEMO_DATA_SOURCE)
    )
    assert seeded_ingredients == 30
    assert db_session.scalar(select(func.count()).select_from(Dish)) >= 20
    assert db_session.scalar(select(func.count()).select_from(NutritionStandard)) == 4
    # 8 周历史：同星期移动平均的每个星期几有 8 个样本，回测才有意义
    # 以当天为界：开发库里可能留着端到端用例造的未来日期的菜单与采集记录，
    # 它们不属于种子历史，也不该让这条断言跟着变
    today = today_local()
    assert (
        db_session.scalar(select(func.count()).select_from(MenuDay).where(MenuDay.date <= today))
        == HISTORY_DAYS
    )
    assert (
        db_session.scalar(select(func.count()).select_from(DailyLog).where(DailyLog.date <= today))
        == HISTORY_DAYS
    )


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

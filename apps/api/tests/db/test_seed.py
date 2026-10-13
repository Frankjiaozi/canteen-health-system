"""种子数据的幂等性与完整性。

这些用例会写开发库，但种子脚本本身是幂等的（按确定性 UUID 覆盖），
因此重复执行不会造成数据漂移。
"""

from __future__ import annotations

from app.db.seed import DEMO_DATA_SOURCE, run
from app.db.session import get_session_factory
from app.modules.collection.models import DailyLog, DailyLogItem
from app.modules.dish.models import Dish, RecipeItem
from app.modules.ingredient.models import Ingredient
from app.modules.menu.models import MenuDay, MenuDayItem
from app.modules.nutrition.models import NutritionStandard
from sqlalchemy import func, select
from sqlalchemy.orm import Session


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
    """验收要求：不少于 20 道菜覆盖一个完整轮换——本阶段先落 5 道可跑通的样板菜。"""
    # 只数种子脚本写入的食材：连同接口测试造的数据一起数会让断言依赖执行顺序
    seeded_ingredients = db_session.scalar(
        select(func.count())
        .select_from(Ingredient)
        .where(Ingredient.data_source == DEMO_DATA_SOURCE)
    )
    assert seeded_ingredients == 22
    assert db_session.scalar(select(func.count()).select_from(Dish)) == 5
    assert db_session.scalar(select(func.count()).select_from(NutritionStandard)) == 4
    assert db_session.scalar(select(func.count()).select_from(MenuDay)) == 14
    assert db_session.scalar(select(func.count()).select_from(DailyLog)) == 14


def test_every_dish_has_at_least_one_recipe_item(db_session: Session) -> None:
    """没有配方的菜品无法参与营养计算，属于必须拦住的数据缺陷。"""
    dish_ids = set(db_session.scalars(select(Dish.id)))
    with_recipe = set(db_session.scalars(select(RecipeItem.dish_id).distinct()))

    assert dish_ids
    assert dish_ids - with_recipe == set(), "存在没有配方明细的菜品"


def test_recipe_items_reference_existing_ingredients(db_session: Session) -> None:
    ingredient_ids = set(db_session.scalars(select(Ingredient.id)))
    referenced = set(db_session.scalars(select(RecipeItem.ingredient_id).distinct()))

    assert referenced
    assert referenced <= ingredient_ids, "配方引用了不存在的食材"


def test_history_links_menu_items_and_daily_items(db_session: Session) -> None:
    """菜单日与每日记录的明细必须一一对应，否则闭环不完整。"""
    menu_pairs = set(
        db_session.execute(
            select(MenuDay.date, MenuDayItem.dish_id).join(
                MenuDayItem, MenuDayItem.menu_day_id == MenuDay.id
            )
        )
    )
    log_pairs = set(
        db_session.execute(
            select(DailyLog.date, DailyLogItem.dish_id).join(
                DailyLogItem, DailyLogItem.daily_log_id == DailyLog.id
            )
        )
    )

    assert menu_pairs
    assert menu_pairs == log_pairs, "菜单供应的菜品与每日记录的菜品不一致"


def test_submitted_logs_record_who_and_when(db_session: Session) -> None:
    logs = list(db_session.scalars(select(DailyLog)))

    assert logs
    for log in logs:
        assert log.submitted_by is not None, f"{log.date} 缺少提交人"
        assert log.submitted_at is not None, f"{log.date} 缺少提交时间"

"""菜单推荐的行为约定。

求解器是纯函数，用构造数据就能把「硬约束逐条成立」验清楚；
接口部分盯的是「落库的快照能自解释、否决必须写原因、权限分得清」。
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from app.modules.dish.models import Dish
from app.modules.menu.models import MenuDay, MenuDayItem
from app.modules.recommendation import repository, solver, targets
from app.modules.recommendation.models import MenuSuggestion
from app.shared.enums import CookingMethod, DishCategory, MealType, SuggestionStatus
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.helpers import today_local

BASE = "/api/v1/recommendation"


def _dish(
    name: str,
    *,
    energy: str = "200",
    salt: str = "1.0",
    oil: str = "3.0",
    cost: str = "1.5",
    popularity: str = "300",
    category: DishCategory = DishCategory.HALF_MEAT,
    method: CookingMethod = CookingMethod.STIR_FRY,
    ingredients: tuple[UUID, ...] | None = None,
) -> solver.CandidateDish:
    return solver.CandidateDish(
        dish_id=uuid4(),
        name=name,
        category=category,
        cooking_method=method,
        energy_kcal=Decimal(energy),
        protein_g=Decimal("8"),
        fat_g=Decimal("6"),
        carb_g=Decimal("25"),
        sodium_mg=Decimal("400"),
        oil_g=Decimal(oil),
        salt_g=Decimal(salt),
        sugar_g=Decimal("0"),
        cost_per_serving=Decimal(cost),
        popularity=Decimal(popularity),
        ingredient_ids=frozenset(ingredients or (uuid4(),)),
    )


def _constraints(**overrides: object) -> solver.PlanConstraints:
    base: dict[str, object] = {
        "targets": (
            solver.PlanTarget("energy_kcal", "能量", "千卡", Decimal("700"), Decimal("900")),
            solver.PlanTarget("SALT", "食盐", "g", None, Decimal("5")),
        ),
        "budget": Decimal("2000"),
        "diner_count": 200,
        "dish_count_min": 3,
        "dish_count_max": 5,
        "serving_ratio_min": Decimal("0.5"),
        "serving_ratio_max": Decimal("1.5"),
        "max_method_ratio": Decimal("0.5"),
        "min_ingredient_kinds": 1,
        "category_min": {},
        "category_max": {},
        "excluded_dish_ids": frozenset(),
    }
    base.update(overrides)
    return solver.PlanConstraints(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 求解器：硬约束逐条验证
# ---------------------------------------------------------------------------
def test_fixed_plan_takes_the_servings_it_is_given_and_chooses_nothing() -> None:
    """早餐那条路：给定菜品与份数，只算供给与成本，不做任何选择。

    口径必须与求解出来的那条完全一样（同一套折算与取整），否则早餐与午晚餐的
    差距分析没法并排看——所以这里连人均值都手算一遍。
    """
    dishes = [
        _dish(
            "白粥",
            energy="30",
            salt="0",
            oil="0",
            cost="0.4",
            category=DishCategory.STAPLE,
            method=CookingMethod.BOIL,
        ),
        _dish(
            "煮鸡蛋",
            energy="78",
            salt="0.1",
            oil="0",
            cost="0.7",
            category=DishCategory.HALF_MEAT,
            method=CookingMethod.BOIL,
        ),
    ]
    constraints = _constraints(
        targets=(
            solver.PlanTarget("energy_kcal", "能量", "千卡", Decimal("400"), Decimal("600")),
            solver.PlanTarget("SALT", "食盐", "g", None, Decimal("5")),
        ),
        fixed_servings={
            dishes[0].dish_id: Decimal("600"),
            dishes[1].dish_id: Decimal("800"),
        },
    )

    plan = solver.fixed_plan(dishes, constraints=constraints)

    # 两道菜都留下，没有被「优化」掉
    assert {item.dish_id for item in plan.items} == {dish.dish_id for dish in dishes}
    assert plan.solver_status == "FIXED"
    # 人均能量 = (30×600 + 78×800) ÷ 200 人次 = 402 千卡
    assert plan.per_capita["energy_kcal"] == Decimal("402.000")
    # 人均盐 = (0×600 + 0.1×800) ÷ 200 = 0.4 克
    assert plan.per_capita["SALT"] == Decimal("0.400")
    # 成本 = 0.4×600 + 0.7×800 = 800 元
    assert plan.cost == Decimal("800.00")


def test_plan_satisfies_every_hard_constraint() -> None:
    """需求要求「生成的菜单满足全部硬约束」，那就逐条量一遍。"""
    pool = [
        # 烹饪方式必须错开：「炒菜不超过一半」和「至少三道菜」放在一起，
        # 全是炒菜的候选集直接无解——这不是模型的毛病，是候选集不成立
        _dish(
            "甲",
            energy="200",
            salt="1.0",
            cost="1.2",
            category=DishCategory.MEAT,
            method=CookingMethod.STEW,
        ),
        _dish(
            "乙",
            energy="180",
            salt="1.2",
            cost="1.4",
            category=DishCategory.VEGETABLE,
            method=CookingMethod.STIR_FRY,
        ),
        _dish(
            "丙",
            energy="150",
            salt="0.8",
            cost="0.6",
            category=DishCategory.SOUP,
            method=CookingMethod.BOIL,
        ),
        _dish(
            "丁",
            energy="260",
            salt="0.5",
            cost="0.4",
            category=DishCategory.STAPLE,
            method=CookingMethod.STEAM,
        ),
        _dish(
            "戊",
            energy="120",
            salt="1.1",
            cost="1.0",
            category=DishCategory.HALF_MEAT,
            method=CookingMethod.COLD_DRESS,
        ),
    ]
    constraints = _constraints()

    plan = solver.solve_menu(pool, constraints)

    chosen = len(plan.items)
    assert constraints.dish_count_min <= chosen <= constraints.dish_count_max
    assert plan.cost <= constraints.budget
    assert plan.per_capita["energy_kcal"] >= Decimal("700")
    assert plan.per_capita["SALT"] <= Decimal("5")
    total_servings = sum((item.servings for item in plan.items), Decimal("0"))
    assert total_servings > 0
    for item in plan.items:
        ratio = item.servings / Decimal(constraints.diner_count)
        assert constraints.serving_ratio_min <= ratio <= constraints.serving_ratio_max


def test_method_ratio_is_respected() -> None:
    """炒菜不超过总数的一半——这条得能在结果上验出来。"""
    pool = [
        _dish("炒一", method=CookingMethod.STIR_FRY, energy="200"),
        _dish("炒二", method=CookingMethod.STIR_FRY, energy="200"),
        _dish("炒三", method=CookingMethod.STIR_FRY, energy="200"),
        _dish("蒸一", method=CookingMethod.STEAM, energy="200"),
        _dish("炖一", method=CookingMethod.STEW, energy="200"),
    ]
    constraints = _constraints(dish_count_min=3, dish_count_max=4)

    plan = solver.solve_menu(pool, constraints, weights=solver.PlanWeights(popularity=Decimal("0")))

    stir = [item for item in plan.items if item.name.startswith("炒")]
    assert len(stir) <= len(plan.items) / 2


def test_other_meal_uses_one_authoritative_source(db_session: Session) -> None:
    """同一天另一餐只取一个权威来源：有菜单日就按菜单日，别把过期的那版并进来。

    并起来会把**已经作废的旧版本**也算进去。实测过一次真实后果：三样汤分别被
    「昨天午餐的菜」「今天晚餐的菜单日」「今天晚餐那版过期推荐」各排除一样，
    午餐直接排不出来——而其中一条本该已经是历史版本。
    """
    target = today_local() + timedelta(days=40)
    dish_ids = {row.name: row.id for row in db_session.scalars(select(Dish))}

    menu_day = MenuDay(date=target, meal_type=MealType.DINNER)
    db_session.add(menu_day)
    db_session.flush()
    db_session.add(
        MenuDayItem(
            menu_day_id=menu_day.id,
            dish_id=dish_ids["红烧肉"],
            planned_servings=Decimal("100"),
        )
    )
    # 同一餐还有一版更早生成、没被采纳的推荐：它已经被菜单日取代了
    db_session.add(
        MenuSuggestion(
            date=target,
            meal_type=MealType.DINNER,
            candidate_menu=[{"dish_id": str(dish_ids["清蒸鲈鱼"]), "dish_name": "清蒸鲈鱼"}],
        )
    )
    db_session.flush()

    found = repository.load_other_meal_dishes(db_session, on_date=target, meal_type=MealType.LUNCH)

    assert dish_ids["红烧肉"] in found
    assert dish_ids["清蒸鲈鱼"] not in found


def test_excluded_dishes_are_not_recommended() -> None:
    """同一道菜不连续两日重复：昨天供应的菜要被排除干净。"""
    yesterday = _dish("昨天的菜", energy="200")
    pool = [
        yesterday,
        _dish("甲", method=CookingMethod.STEW),
        _dish("乙", method=CookingMethod.STIR_FRY),
        _dish("丙", method=CookingMethod.BOIL),
    ]
    constraints = _constraints(excluded_dish_ids=frozenset({yesterday.dish_id}))

    plan = solver.solve_menu(pool, constraints)

    assert yesterday.dish_id not in {item.dish_id for item in plan.items}


def test_category_limits_prevent_silly_menus() -> None:
    """没有类别的上下限，求解器会交出「两道汤加三道蛋菜」——营养挑不出毛病，但不是一餐饭。"""
    pool = [
        _dish("汤一", category=DishCategory.SOUP, energy="100"),
        _dish("汤二", category=DishCategory.SOUP, energy="100", method=CookingMethod.BOIL),
        _dish("汤三", category=DishCategory.SOUP, energy="100", method=CookingMethod.STEAM),
        _dish("饭", category=DishCategory.STAPLE, energy="260", method=CookingMethod.STEAM),
        _dish("菜", category=DishCategory.VEGETABLE, energy="150", method=CookingMethod.STEW),
    ]
    constraints = _constraints(
        category_min={DishCategory.STAPLE: 1, DishCategory.SOUP: 1, DishCategory.VEGETABLE: 1},
        category_max={DishCategory.SOUP: 1, DishCategory.STAPLE: 2},
    )

    plan = solver.solve_menu(pool, constraints)

    soups = [item for item in plan.items if item.name.startswith("汤")]
    assert len(soups) == 1


def test_infeasible_budget_is_explained() -> None:
    """解不出来时要指出卡在哪条约束上，而不是丢一句「无解」。"""
    pool = [_dish("贵一", cost="40"), _dish("贵二", cost="50"), _dish("贵三", cost="60")]
    constraints = _constraints(budget=Decimal("10"))

    with pytest.raises(solver.InfeasibleError) as error:
        solver.solve_menu(pool, constraints)

    assert "预算" in " ".join(error.value.conflicts)


def test_infeasible_seasoning_floor_is_explained() -> None:
    """份数给定之后，「少做点」这条退路没了，诊断要按「最少几道菜的合计」算。

    这一条是实测踩出来的：录进来的就餐人次远小于预测份数时，人均油盐糖会被放大，
    而求解器只能用「换菜」来降——换不动的时候，得让人看清是哪个量压不下去。
    """
    pool = [_dish(f"菜{index}", salt="1.5") for index in range(5)]
    fixed = {dish.dish_id: Decimal("400") for dish in pool}
    constraints = _constraints(diner_count=100, fixed_servings=fixed)

    with pytest.raises(solver.InfeasibleError) as error:
        solver.solve_menu(pool, constraints)

    conflicts = " ".join(error.value.conflicts)
    assert "食盐" in conflicts
    assert "超过上限" in conflicts


# ---------------------------------------------------------------------------
# 目标区间怎么来的
# ---------------------------------------------------------------------------
def test_energy_target_is_split_by_meal_and_macros_are_derived(
    db_session: Session,
) -> None:
    """能量按餐次折算；三大营养素由能量 × 供能比 ÷ 每克产能反推。"""
    from app.modules.recommendation import repository

    standards = repository.load_standards(db_session)
    plan_targets, basis = targets.build_targets(MealType.LUNCH, standards)
    by_code = {target.code: target for target in plan_targets}

    share = targets.meal_share(MealType.LUNCH)
    assert by_code["energy_kcal"].upper == Decimal(str(get_settings_value("max"))) * share
    # 脂肪的每克产能是 9 千卡，上限 30%
    expected_fat = (
        Decimal(str(get_settings_value("max"))) * Decimal("0.30") / Decimal("9") * share
    ).quantize(Decimal("0.1"))
    assert by_code["fat_g"].upper == expected_fat
    assert basis["energy_verified"] is False, "能量目标是演示值，必须如实标注待核实"


def test_seasoning_caps_use_daily_limits_not_meal_scaled(db_session: Session) -> None:
    """油盐糖取每日上限。按餐次折算会让模型必然无解，这一点要显式守住。"""
    from app.modules.recommendation import repository

    standards = repository.load_standards(db_session)
    plan_targets, _ = targets.build_targets(MealType.LUNCH, standards)
    by_code = {target.code: target for target in plan_targets}

    assert by_code["SALT"].upper == Decimal("5.000")
    assert by_code["SALT"].lower is None, "食盐只有上限"
    assert by_code["EDIBLE_OIL"].upper == Decimal("30.000")
    assert by_code["EDIBLE_OIL"].lower is None, "推荐摄入量的下限不该变成「必须用够这么多油」"


def get_settings_value(kind: str) -> int:
    from app.core.config import get_settings

    settings = get_settings()
    return (
        settings.nutrition_energy_target_kcal
        if kind == "max"
        else settings.nutrition_energy_target_min_kcal
    )


# ---------------------------------------------------------------------------
# 接口
# ---------------------------------------------------------------------------
def test_generate_returns_menu_with_gaps_and_reasons(as_recorder: TestClient) -> None:
    target = today_local() + timedelta(days=1)

    response = as_recorder.post(
        f"{BASE}/generate", params={"on_date": target.isoformat(), "meal_type": "LUNCH"}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert 4 <= len(body["dishes"]) <= 6
    assert body["status"] == "PENDING"
    # 差距分析要给出缺口多大，只给「达标 / 不达标」的标签不算完成
    assert body["gaps"]
    for gap in body["gaps"]:
        assert gap["status"] in {"ok", "over", "under"}
        assert gap["target_text"]
        assert Decimal(gap["gap"]) >= 0
        if gap["status"] == "ok":
            assert Decimal(gap["gap"]) == 0
    # 每条推荐都要说得出原因
    assert body["reasons"]
    assert all(reason["text"] for reason in body["reasons"])
    assert body["target_basis"]["energy_verified"] is False
    assert body["solver_status"] == "Optimal"


def test_generated_menu_satisfies_the_constraints_it_claims(
    as_recorder: TestClient, db_session: Session
) -> None:
    """把接口返回的菜单对着约束逐条复核一遍。"""
    target = today_local() + timedelta(days=2)
    as_recorder.post(
        f"{BASE}/generate", params={"on_date": target.isoformat(), "meal_type": "LUNCH"}
    )

    db_session.expire_all()
    saved = db_session.scalar(select(MenuSuggestion).where(MenuSuggestion.date == target))
    assert saved is not None
    # 落库的快照必须自包含：菜单、差距、理由、目标口径都要在里面
    assert saved.candidate_menu and saved.reasons
    assert saved.nutrition_gap["target_basis"]["energy_verified"] is False
    assert saved.cost_estimate is not None

    budget = Decimal(str(saved.nutrition_gap["budget"]))
    total = sum((Decimal(str(row["cost"])) for row in saved.candidate_menu), Decimal("0"))
    assert total <= budget, "菜单成本不能超预算"


def test_saved_menu_is_readable_afterwards(as_recorder: TestClient) -> None:
    """读回来的内容要与生成时一致——落库快照就是当初给人看的那份。"""
    target = today_local() + timedelta(days=3)
    created = as_recorder.post(
        f"{BASE}/generate", params={"on_date": target.isoformat(), "meal_type": "LUNCH"}
    ).json()

    fetched = as_recorder.get(f"{BASE}/{created['id']}").json()

    assert fetched["dishes"] == created["dishes"]
    assert fetched["cost_estimate"] == created["cost_estimate"]
    assert len(fetched["reasons"]) == len(created["reasons"])


def test_history_lists_previous_suggestions(as_recorder: TestClient) -> None:
    target = today_local() + timedelta(days=4)
    as_recorder.post(
        f"{BASE}/generate", params={"on_date": target.isoformat(), "meal_type": "LUNCH"}
    )

    rows = as_recorder.get(f"{BASE}", params={"on_date": target.isoformat()}).json()

    assert rows and rows[0]["date"] == target.isoformat()
    assert rows[0]["dish_count"] >= 4
    assert rows[0]["status_label"]


def test_reject_requires_a_reason(as_recorder: TestClient) -> None:
    """否决必须写明原因——需求里写明它会被用来改进后续推荐。"""
    target = today_local() + timedelta(days=5)
    created = as_recorder.post(
        f"{BASE}/generate", params={"on_date": target.isoformat(), "meal_type": "LUNCH"}
    ).json()

    without = as_recorder.post(f"{BASE}/{created['id']}/decide", json={"status": "REJECTED"})
    assert without.status_code == 422
    assert "原因" in without.json()["message"]

    with_reason = as_recorder.post(
        f"{BASE}/{created['id']}/decide",
        json={"status": "REJECTED", "reason": "周五学生普遍不留校吃午饭"},
    )
    assert with_reason.status_code == 200
    assert with_reason.json()["status"] == "REJECTED"
    assert with_reason.json()["rejected_reason"] == "周五学生普遍不留校吃午饭"


def test_accept_records_the_decision(as_recorder: TestClient) -> None:
    target = today_local() + timedelta(days=6)
    created = as_recorder.post(
        f"{BASE}/generate", params={"on_date": target.isoformat(), "meal_type": "LUNCH"}
    ).json()

    accepted = as_recorder.post(
        f"{BASE}/{created['id']}/decide", json={"status": "ACCEPTED"}
    ).json()

    assert accepted["status"] == SuggestionStatus.ACCEPTED.value
    assert accepted["decided_at"] is not None


def test_cannot_go_back_to_pending(as_recorder: TestClient) -> None:
    target = today_local() + timedelta(days=7)
    created = as_recorder.post(
        f"{BASE}/generate", params={"on_date": target.isoformat(), "meal_type": "LUNCH"}
    ).json()

    response = as_recorder.post(f"{BASE}/{created['id']}/decide", json={"status": "PENDING"})

    assert response.status_code == 422


def test_unknown_suggestion_is_reported(as_recorder: TestClient) -> None:
    response = as_recorder.get(f"{BASE}/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_requires_login(client: TestClient) -> None:
    assert client.get(BASE).status_code == 401
    assert client.post(f"{BASE}/generate").status_code == 401


def test_school_admin_cannot_generate_or_decide(as_school_admin: TestClient) -> None:
    """推荐只作为建议，最终由食堂管理员确认；学校管理方是只读的观察者。"""
    assert as_school_admin.get(BASE).status_code == 200

    target = today_local() + timedelta(days=8)
    response = as_school_admin.post(f"{BASE}/generate", params={"on_date": target.isoformat()})
    assert response.status_code == 403

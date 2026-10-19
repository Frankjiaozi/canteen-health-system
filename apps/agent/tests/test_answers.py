from copy import deepcopy

from test_agent import PLAN, TODAY

from zhiwei_agent.schemas import PlanParameters, PlanVersion


def version():
    plan = deepcopy(PLAN)
    plan["calculation_version"] = "menu-plan-20261019.1"
    return PlanVersion(
        revision=1,
        created_at="2026-10-19T00:00:00+08:00",
        parameters=PlanParameters(on_date=TODAY),
        result=plan,
    )


def test_plan_answer_keeps_business_numbers_and_per_capita_scope():
    from zhiwei_agent.answers import plan_summary

    saved = version()
    result = plan_summary(saved)
    assert "整餐人均营养供给" in result
    assert "供给量不等于实际摄入量" in result
    for row in saved.result["gaps"]:
        assert str(row["actual"]) in result
    assert saved.result["total_cost"] in result
    assert "单份口径" not in result and "预算占用率" not in result


def test_plan_answer_distinguishes_missing_from_zero_without_recomputing():
    from zhiwei_agent.answers import plan_summary

    saved = version()
    saved.result["total_cost"] = 0
    saved.result["gaps"][0]["actual"] = None
    saved.result["missing_price_warning"] = "有原料未录入单价"
    result = plan_summary(saved)
    assert "已知价格部分合计：0 元" in result
    assert "能量：未提供" in result
    assert "有原料未录入单价" in result


def test_plan_answer_handles_withdrawal_and_only_compares_saved_values():
    from zhiwei_agent.answers import plan_summary

    previous, current = version(), version()
    current.revision = 2
    current.result["total_cost"] = "999.99"
    current.undone = {"undone_by": "演示用户"}
    result = plan_summary(current, previous)
    assert "已撤回" in result
    assert "重新生成" in result
    assert f"{previous.result['total_cost']} → 999.99" in result
    assert "节省" not in result and "%" not in result

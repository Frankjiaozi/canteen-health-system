"""菜单回答的事实段：只展示保存的业务字段，不让模型重算或改写数值口径。"""

from .schemas import PlanVersion

GAP_STATUS = {"ok": "在目标区间", "under": "低于目标", "over": "高于目标"}


def value(item) -> str:
    return "未提供" if item is None or item == "" else str(item)


def plan_summary(version: PlanVersion, previous: PlanVersion | None = None) -> str:
    plan = version.result
    cost_label = "已知价格部分合计" if plan.get("missing_price_warning") else "采购合计"
    lines = [
        f"第 {version.revision} 版 · {version.publication_label}",
        f"{plan['date']} {plan['meal_type_label']}，预计 {plan['diner_count']} 人次。",
        f"每人预算：{value(plan.get('budget_per_person') or version.parameters.budget_per_person)} 元；总预算：{value(plan.get('budget'))} 元。",
        f"{cost_label}：{value(plan.get('total_cost'))} 元。",
        "",
        "菜单与计划供应份数：",
    ]
    for row in plan.get("dishes", []):
        servings = row.get("planned_servings")
        if servings is None:
            servings = row.get("predicted_servings")
        lines.append(
            f"- {row['dish_name']}：{value(servings)} 份；{value(row.get('nutrition_basis'))}。"
        )
    if plan.get("gaps"):
        lines.extend(["", "整餐人均营养供给（按本餐计划份数和预计人次核算）："])
        for row in plan["gaps"]:
            if row.get("actual") is None:
                lines.append(f"- {row['label']}：未提供，不能判断差距。")
                continue
            status = GAP_STATUS.get(row.get("status"), "状态未提供")
            lines.append(
                f"- {row['label']}：{value(row['actual'])} {row['unit']}；目标 {row['target_text']}，{status}。"
            )
    lines.extend(["", "口径与提醒：", "- 供给量不等于实际摄入量，一餐结果不能证明全天合规。"])
    if version.data_notice:
        lines.append("- " + version.data_notice)
    if plan.get("missing_price_warning"):
        lines.append("- " + plan["missing_price_warning"])
    if plan.get("servings_note"):
        lines.append("- " + plan["servings_note"])
    basis = plan.get("target_basis", {})
    if basis.get("energy_verified") is not True:
        lines.append("- 能量等目标的适用人群和来源仍需核实，不能把求解成功表述为营养全部达标。")
    if basis.get("scope_notice"):
        lines.append("- " + str(basis["scope_notice"]))
    for note in plan.get("notes", [])[:3]:
        lines.append("- " + note)
    if previous is not None:
        old = previous.result
        lines.extend(
            [
                "",
                f"与第 {previous.revision} 版对照（两版保存值）：",
                f"- 人次：{value(old.get('diner_count'))} → {value(plan.get('diner_count'))}。",
                f"- 采购金额：{value(old.get('total_cost'))} → {value(plan.get('total_cost'))} 元。",
                f"- 预算：{value(old.get('budget'))} → {value(plan.get('budget'))} 元。",
            ]
        )
    if version.undone:
        lines.append("\n本版已撤回；如需再次发布，请重新生成并核对。")
    elif version.publication:
        lines.append("\n本版保留发布回执，后续实际供餐仍需完成每日采集。")
    else:
        lines.append("\n当前为草案，核对后可在界面确认发布；尚未写入正式菜单。")
    return "\n".join(lines)

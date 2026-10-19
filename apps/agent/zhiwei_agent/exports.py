import csv
import io

from .schemas import Conversation, PlanVersion


def safe_cell(value) -> str:
    text = str(value if value is not None else "")
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text


def purchase_csv(version: PlanVersion, notice: str) -> bytes:
    notice = version.data_notice or notice
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    plan = version.result
    writer.writerow(
        [
            "知味采购建议",
            f"第 {version.revision} 版",
            version.publication_label,
        ]
    )
    writer.writerow([safe_cell(notice)])
    writer.writerow(
        ["日期", plan["date"], "餐次", plan["meal_type_label"], "人次", plan["diner_count"]]
    )
    writer.writerow(["方案ID", plan["suggestion_id"], "生成时间", version.created_at])
    writer.writerow(["原料", "单位", "采购数量", "单价（元/公斤市品）", "预计金额（元）"])
    for row in plan["requirements"]:
        writer.writerow(
            [
                safe_cell(row.get(key))
                for key in ("name", "unit", "quantity", "unit_price", "estimated_cost")
            ]
        )
    cost = plan.get("total_cost")
    writer.writerow(
        [
            "已知价格部分合计" if plan.get("missing_price_warning") else "合计",
            "",
            "",
            "",
            cost if cost is not None else "金额不完整",
        ]
    )
    writer.writerow(["预算（元）", plan["budget"]])
    writer.writerow([safe_cell(plan["servings_note"])])
    for note in [*plan.get("notes", []), plan.get("missing_price_warning")]:
        if note:
            writer.writerow([safe_cell(note)])
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def review_markdown(conversation: Conversation, notice: str) -> str:
    review = conversation.review.model_dump(mode="json") if conversation.review else None
    if review:
        notice = review.get("data_notice") or notice
    lines = ["# 知味供应记录核查", "", notice, ""]
    if not review:
        return "尚无核查结果"
    lines += [
        f"范围：{review['start']} 至 {review['end']}；{review['record_count']} 份记录，覆盖 {review['days_with_records']} 天。",
        "",
        review["note"],
        "",
    ]
    for issue in review["issues"]:
        lines += [
            f"## {issue['date']} {issue['meal_label']} · {issue['title']}",
            "",
            issue["detail"],
            "",
            issue["suggestion"],
            "",
            f"来源：每日采集 {issue['date']} / {issue['meal_type']}",
            "",
        ]
    lines += ["无记录日期（需核对是否营业）：" + "、".join(review["missing_dates"])]
    return "\n".join(lines)

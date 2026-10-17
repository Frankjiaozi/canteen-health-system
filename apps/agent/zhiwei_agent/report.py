"""自包含的离线核对报告。只呈现保存的业务快照，不让模型重算或润色数值。"""

import json
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from .schemas import PlanVersion

BOUNDARY = "供给量不等于实际摄入量。当前目标与份数策略仍需按服务人群核实，不能据此认证个人健康、营养全部达标或全天合规。"
BASIS_LABELS = {
    "meal_share": "本餐占全天份额",
    "energy_target_kcal": "全天能量演示上限 / 千卡",
    "energy_target_min_kcal": "全天能量演示下限 / 千卡",
    "energy_source": "能量目标依据",
    "energy_verified": "能量目标是否已核实",
    "macro_source": "营养素换算口径",
    "seasoning_source": "油盐糖求解口径",
    "scope_notice": "适用范围提醒",
    "scope_reference": "范围核对来源",
}
STATUS = {"ok": "在目标区间", "under": "低于目标", "over": "高于目标"}


def text(value) -> str:
    if value is None or value == "":
        return "未录"
    if isinstance(value, bool):
        return "是" if value else "否"
    return str(value)


def h(value) -> str:
    return escape(text(value), quote=True)


def timestamp(value) -> str:
    try:
        moment = datetime.fromisoformat(str(value))
        if moment.tzinfo:
            moment = moment.astimezone(ZoneInfo("Asia/Shanghai"))
        return moment.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return text(value)


def table(headers: list[str], rows: list[list]) -> str:
    return (
        "<div class='table-wrap'><table><thead><tr>"
        + "".join(f"<th scope='col'>{h(cell)}</th>" for cell in headers)
        + "</tr></thead><tbody>"
        + "".join("<tr>" + "".join(f"<td>{h(cell)}</td>" for cell in row) + "</tr>" for row in rows)
        + "</tbody></table></div>"
    )


def report_html(version: PlanVersion, notice: str) -> str:
    plan, receipt = version.result, version.publication
    notice = version.data_notice or notice
    historical = not plan.get("calculation_version")
    warnings = [BOUNDARY]
    if historical:
        warnings.append(
            "此版为旧计算规则的历史快照。原数值与文字保留供追溯，建议重新生成再用于新的安排；旧说明不能作为当前标准认证。"
        )
    if plan.get("missing_price_warning"):
        warnings.append(plan["missing_price_warning"])
    for gap in plan["gaps"]:
        if gap["status"] != "ok":
            warnings.append(
                f"{gap['label']}：{gap['actual']} {gap['unit']}，{STATUS.get(gap['status'], gap['status'])}（{gap['target_text']}）。"
            )
    status = "本版曾确认发布" if receipt else "待人工确认的草案"
    confirmation = (
        f"确认人：{h(receipt['published_by'])}；时间：{h(timestamp(receipt['published_at']))}（北京时间）。"
        if receipt
        else "本报告不会发布菜单、生成实际采集或向供应商下单。"
    )
    dishes = [
        [
            row["dish_name"],
            row["category_label"],
            row["cooking_method_label"],
            row.get("planned_servings")
            or row.get("predicted_servings")
            or f"估算 {plan['diner_count']}",
            "降级估算" if row.get("prediction_fallback") else row.get("predicted_basis_label"),
            row["nutrition_basis"],
        ]
        for row in plan["dishes"]
    ]
    nutrients = [
        [
            row["label"],
            f"{row['actual']} {row['unit']}",
            row["target_text"],
            STATUS.get(row["status"], row["status"]),
            row.get("note") or "—",
        ]
        for row in plan["gaps"]
    ]
    purchase = [
        [
            row["name"],
            row["quantity"],
            row["unit"],
            row.get("unit_price"),
            row.get("estimated_cost"),
        ]
        for row in plan["requirements"]
    ]
    basis = [
        [
            BASIS_LABELS.get(key, key),
            json.dumps(value, ensure_ascii=False)
            if isinstance(value, (dict, list))
            else text(value),
        ]
        for key, value in plan["target_basis"].items()
    ]
    readiness = version.readiness
    readiness_section = ""
    if readiness:
        readiness_section = (
            f"<h2>生成前的数据体检</h2><p>检查时间：{h(timestamp(readiness.get('checked_at')))}；可用候选 {h(readiness.get('available_count'))} 道，有预测 {h(readiness.get('predicted_count'))} 道。此项是当时的检查，当前数据可能已变化。</p>"
            + (
                table(
                    ["项目", "具体缺口", "下一步"],
                    [[row["title"], row["detail"], row["action"]] for row in readiness["issues"]],
                )
                if readiness["issues"]
                else "<p>当时结构检查未发现缺口，仍需核对来源与实际供餐背景。</p>"
            )
        )
    css = """
    :root{color-scheme:light}*{box-sizing:border-box}body{margin:0;background:#edf1ed;color:#263b31;font-family:'Microsoft YaHei','PingFang SC',sans-serif;font-size:13px;line-height:1.8}
    main{max-width:1050px;margin:32px auto;background:white;padding:48px 54px}header{border-bottom:2px solid #315c4c;padding-bottom:22px}header .brand{font-family:'KaiTi',serif;font-size:30px;color:#315c4c}h1{font-size:25px;margin:12px 0 4px}h2{font-size:17px;margin:30px 0 12px}p{margin:8px 0}small,.muted{color:#637469}a{color:#315c4c}.status{display:inline-block;background:#edf3ee;border:1px solid #c8d9ca;padding:3px 10px;border-radius:3px;margin-bottom:12px}.notice{background:#f6f3e9;border-left:3px solid #ac9873;padding:12px 15px;margin:20px 0}.facts{display:grid;grid-template-columns:repeat(4,1fr);gap:15px;border-bottom:1px solid #dce5de;padding:20px 0}.facts span{font-size:11px;color:#637469}.facts strong{display:block;font-size:20px;font-weight:600}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;font-size:12px}th{text-align:left;background:#edf3ee;font-weight:600}td,th{padding:9px 10px;border-bottom:1px solid #dce5de;vertical-align:top}td{white-space:normal;overflow-wrap:anywhere}ul,ol{padding-left:22px}.warning li{margin:7px 0}.warning{background:#fff9ef;padding:12px 16px 12px 32px;border:1px solid #eee1c6}code{overflow-wrap:anywhere;font-size:11px}footer{border-top:1px solid #dce5de;margin-top:32px;padding-top:15px;font-size:11px;color:#637469}
    @page{size:A4;margin:14mm}@media print{body{background:white}main{max-width:none;margin:0;padding:0}header,h2,tr,.facts{break-inside:avoid}thead{display:table-header-group}a{color:inherit;text-decoration:none}.table-wrap{overflow:visible}.print-tip{display:none}}@media(max-width:650px){main{margin:0;padding:26px 18px}.facts{grid-template-columns:repeat(2,1fr)}h1{font-size:21px}table{min-width:560px}}
    """
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"><title>知味 · {h(plan["date"])}{h(plan["meal_type_label"])} 第{version.revision}版</title><style>{css}</style></head><body><main>
    <header><div class="brand">知味</div><h1>供餐安排与采购核对单</h1><p>{h(plan["date"])} {h(plan["meal_type_label"])} · 第 {version.revision} 版</p><small>生成时间 {h(timestamp(version.created_at))}（北京时间）</small></header>
    <div class="notice">{h(notice)}</div><span class="status">{status}</span><p>{confirmation}</p>
    <div class="facts"><div><span>预计就餐人次</span><strong>{h(plan["diner_count"])}</strong></div><div><span>每人预算 / 元</span><strong>{h(plan.get("budget_per_person") or version.parameters.budget_per_person)}</strong></div><div><span>总预算 / 元</span><strong>{h(plan["budget"])}</strong></div><div><span>{"已知价格部分合计" if plan.get("missing_price_warning") else "预计采购合计"} / 元</span><strong>{h(plan.get("total_cost"))}</strong></div></div>
    <h2>核对后再决定</h2><ul class="warning">{"".join(f"<li>{h(note)}</li>" for note in warnings)}</ul>
    <h2>菜单与计划份数</h2>{table(["菜品", "类别", "烹调", "计划份数", "份数依据", "营养口径"], dishes)}
    <h2>人均供给与建议目标</h2>{table(["指标", "计算供给量", "当前目标", "差距", "口径说明"], nutrients)}
    <h2>采购明细</h2><p>{h(plan["servings_note"])}</p>{table(["原料", "数量", "单位", "单价 / 元每公斤市品", "预计金额 / 元"], purchase)}<p><strong>{"已知价格部分合计" if plan.get("missing_price_warning") else "采购预计合计"}：{h(plan.get("total_cost"))} 元；总预算 {h(plan["budget"])} 元。</strong></p><p>金额为快照中的逐项结果。未录单价不等于免费，缺项时合计不是完整成本。</p>
    <h2>条件与计算依据</h2><ol>{"".join(f"<li>{h(note)}</li>" for note in [*plan["notes"], *plan.get("calendar_notes", [])])}</ol><p>本版排除的菜：{h("、".join(plan.get("excluded_dishes", [])) or "无")}</p><ul>{"".join(f"<li>{h(row['text'])}</li>" for row in plan["reasons"])}</ul>
    {readiness_section}<h2>保存的目标口径</h2>{table(["字段说明", "快照记录（含当时口径，需结合上方提醒核对）"], basis)}
    <footer><p>方案编号 <code>{h(plan["suggestion_id"])}</code></p><p>计算规则 <code>{h(plan.get("calculation_version") or "历史版本未记录")}</code>；快照 <code>{h(plan.get("snapshot_token"))}</code></p><p>{BOUNDARY}</p><p class="print-tip">报告可离线查看。需要 PDF 时，使用浏览器“打印 → 另存为 PDF”；无需联网加载字体、图片或脚本。</p></footer></main></body></html>"""

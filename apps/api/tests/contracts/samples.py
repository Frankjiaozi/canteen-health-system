"""S01–S06 联调样例。

这些字典不是“差不多像响应”的 JSON，而是必须通过当前 Pydantic 模型校验的固定样例。
日期、份数、金额和 token 均为样例值，不对应生产数据。
"""

from copy import deepcopy

TOKEN_A = "a" * 64
TOKEN_B = "b" * 64
SUGGESTION_ID = "11111111-1111-4111-8111-111111111111"
MENU_DAY_ID = "22222222-2222-4222-8222-222222222222"
DISH_TOMATO_ID = "33333333-3333-4333-8333-333333333333"
DISH_RICE_ID = "44444444-4444-4444-8444-444444444444"


S01_NORMAL = {
    "date": "2026-10-20",
    "meal_type": "LUNCH",
    "meal_type_label": "午餐",
    "diner_count": 922,
    "suggestion_id": SUGGESTION_ID,
    "dishes": [
        {
            "dish_id": DISH_TOMATO_ID,
            "dish_name": "番茄炒蛋",
            "category_label": "半荤",
            "cooking_method_label": "炒",
            "energy_kcal": "150.62",
            "salt_g": "1.200",
            "popularity": "484",
            "nutrition_basis": "按标准配方推算",
            "predicted_servings": "560.90",
            "predicted_basis_label": "同星期几平均",
            "prediction_fallback": False,
            "planned_servings": "560.90",
        },
        {
            "dish_id": DISH_RICE_ID,
            "dish_name": "米饭",
            "category_label": "主食",
            "cooking_method_label": "蒸",
            "energy_kcal": "276.80",
            "salt_g": "0.000",
            "popularity": "704",
            "nutrition_basis": "按标准配方推算",
            "predicted_servings": "736.00",
            "predicted_basis_label": "同星期几平均",
            "prediction_fallback": False,
            "planned_servings": "736.00",
        },
    ],
    "gaps": [
        {
            "code": "ENERGY",
            "label": "能量",
            "unit": "千卡",
            "target_text": "720 ~ 800千卡",
            "actual": "784.19",
            "status": "ok",
            "gap": "0",
            "note": None,
        },
        {
            "code": "SALT",
            "label": "食盐",
            "unit": "g",
            "target_text": "≤ 2.00g",
            "actual": "3.13",
            "status": "over",
            "gap": "1.13",
            "note": "按餐次折算展示，求解时使用每日上限",
        },
        {
            "code": "EDIBLE_OIL",
            "label": "烹调油",
            "unit": "g",
            "target_text": "≤ 12.00g",
            "actual": "12.81",
            "status": "over",
            "gap": "0.81",
            "note": None,
        },
        {
            "code": "ADDED_SUGAR",
            "label": "添加糖",
            "unit": "g",
            "target_text": "≤ 20.00g",
            "actual": "4.40",
            "status": "ok",
            "gap": "0",
            "note": None,
        },
    ],
    "reasons": [
        {"kind": "popularity", "text": "米饭在历史供应里平均出餐 704 份"},
        {"kind": "variety", "text": "这一餐覆盖炒、蒸两种烹饪方式"},
    ],
    "requirements": [
        {
            "name": "大米",
            "unit": "公斤",
            "quantity": "58.900",
            "unit_price": "5.60",
            "estimated_cost": "329.84",
        },
        {
            "name": "鸡蛋",
            "unit": "公斤",
            "quantity": "33.700",
            "unit_price": "9.60",
            "estimated_cost": "323.52",
        },
        {
            "name": "食盐",
            "unit": "公斤",
            "quantity": "0.700",
            "unit_price": "2.50",
            "estimated_cost": "1.75",
        },
    ],
    "total_cost": "655.11",
    "budget": "7376.00",
    "target_basis": {
        "meal_share": "0.4",
        "energy_target_kcal": 2000,
        "energy_target_min_kcal": 1800,
        "macro_source": "能量 × 供能比 ÷ 每克产能",
        "seasoning_source": "每日上限，未按餐次折算",
    },
    "missing_price_warning": None,
    "excluded_dishes": [],
    "calendar_notes": [],
    "skipped_predictions": [],
    "servings_note": "采购量 = 推荐选出的菜 × 该菜预测份数。",
    "notes": [],
    "snapshot_token": TOKEN_A,
    "expected_menu_token": TOKEN_B,
    "budget_per_person": "8.00",
    "requested_excluded_dish_ids": [],
    "calculation_version": "menu-plan-20261017.3",
}


S02_NO_HISTORY = {
    "readiness": {
        "checked_at": "2026-10-19T12:00:00+08:00",
        "on_date": "2026-10-20",
        "meal_type": "DINNER",
        "meal_type_label": "晚餐",
        "state": "blocked",
        "active_dish_count": 0,
        "candidate_count": 0,
        "available_count": 0,
        "excluded_count": 0,
        "predicted_count": 0,
        "history_start": "2026-08-25",
        "history_end": "2026-10-19",
        "history_record_count": 0,
        "days_with_records": 0,
        "latest_record_date": None,
        "latest_diner_count": None,
        "predicted_diner_count": None,
        "diner_count_lower": None,
        "diner_count_upper": None,
        "diner_count_basis": None,
        "diner_count_basis_label": None,
        "missing_price_count": 0,
        "missing_nutrition_count": 0,
        "categories": [],
        "issues": [
            {
                "code": "insufficient_candidates",
                "severity": "blocking",
                "title": "可用候选菜不足",
                "detail": "当前有 0 道可用，菜单至少需要 4 道。",
                "action": "补齐配方与真实供餐历史，或减少排除条件。",
                "link": "/admin/dishes",
                "entity_id": None,
            }
        ],
        "issue_count": 1,
        "truncated": False,
        "note": "样例：没有可用历史，生成必须被阻止。",
    },
    "error": {
        "status": 422,
        "body": {
            "code": "business_rule_violated",
            "message": "没有可用于推荐的菜品",
            "details": {"conflicts": ["可用候选菜不足"]},
        },
    },
}


S03_MISSING_DATA = deepcopy(S01_NORMAL)
S03_MISSING_DATA["missing_price_warning"] = "部分原料缺单价，金额只是已知部分合计"
S03_MISSING_DATA["requirements"].append(
    {
        "name": "白砂糖",
        "unit": "公斤",
        "quantity": "1.500",
        "unit_price": None,
        "estimated_cost": None,
    }
)


S04_ERRORS = [
    {
        "status": 422,
        "body": {
            "code": "validation_error",
            "message": "请求参数校验失败",
            "details": [
                {
                    "field": "diner_count",
                    "message": "Input should be greater than or equal to 1",
                    "type": "greater_than_equal",
                }
            ],
        },
    },
    {
        "status": 403,
        "body": {
            "code": "forbidden",
            "message": "当前账号没有执行该操作的权限",
            "details": None,
        },
    },
    {
        "status": 404,
        "body": {
            "code": "not_found",
            "message": "请求的资源不存在",
            "details": None,
        },
    },
]


S05_PUBLISH = {
    "success": {
        "suggestion_id": SUGGESTION_ID,
        "menu_day_id": MENU_DAY_ID,
        "on_date": "2026-10-20",
        "meal_type": "LUNCH",
        "dish_count": 2,
        "published_at": "2026-10-19T12:00:00+08:00",
        "published_by": "食堂管理员",
        "already_published": False,
    },
    "repeat": {
        "suggestion_id": SUGGESTION_ID,
        "menu_day_id": MENU_DAY_ID,
        "on_date": "2026-10-20",
        "meal_type": "LUNCH",
        "dish_count": 2,
        "published_at": "2026-10-19T12:00:00+08:00",
        "published_by": "食堂管理员",
        "already_published": True,
    },
    "conflicts": [
        {
            "status": 409,
            "body": {
                "code": "conflict",
                "message": "这餐菜单已被其他人修改，请重新生成并核对后再发布。",
                "details": None,
            },
        },
        {
            "status": 409,
            "body": {
                "code": "conflict",
                "message": "这餐已有实际采集记录，不能用计划覆盖实际供应。",
                "details": None,
            },
        },
    ],
}


S06_UNDO = {
    "success": {
        "suggestion_id": SUGGESTION_ID,
        "on_date": "2026-10-20",
        "meal_type": "LUNCH",
        "meal_type_label": "午餐",
        "undone_at": "2026-10-19T12:30:00+08:00",
        "undone_by": "食堂管理员",
    },
    "conflicts": [
        {
            "status": 409,
            "body": {
                "code": "conflict",
                "message": "这餐菜单在确认后又被修改，不能撤回覆盖。",
                "details": None,
            },
        },
        {
            "status": 409,
            "body": {
                "code": "conflict",
                "message": "这餐已经录过采集，不能撤回计划覆盖实际供应。",
                "details": None,
            },
        },
    ],
}


SAMPLES = {
    "S01": S01_NORMAL,
    "S02": S02_NO_HISTORY,
    "S03": S03_MISSING_DATA,
    "S04": S04_ERRORS,
    "S05": S05_PUBLISH,
    "S06": S06_UNDO,
}

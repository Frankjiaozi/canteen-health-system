import asyncio
from datetime import date
from uuid import uuid4

from zhiwei_agent.schemas import Conversation, PlanParameters
from zhiwei_agent.tools import Tools, definitions

TODAY = date(2026, 10, 18)
DISH_A = {
    "id": str(uuid4()),
    "name": "番茄炒蛋",
    "category_label": "半荤",
    "cooking_method_label": "炒",
    "recipe_version": 3,
}
DISH_B = {
    "id": str(uuid4()),
    "name": "煮鸡蛋",
    "category_label": "半荤",
    "cooking_method_label": "煮",
    "recipe_version": 1,
}


class BusinessStub:
    """只模拟 HTTP 契约，不模拟业务计算。"""

    def __init__(self):
        self.calls = []

    async def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if path == "dashboard/summary":
            return {
                "days": 30,
                "start": "2026-09-19",
                "end": "2026-10-18",
                "days_with_records": 27,
                "avg_diner_count": 1800,
                "avg_salt_per_capita_g": "4.5",
                "avg_oil_per_capita_g": "16.0",
                "avg_added_sugar_per_capita_g": "5.0",
                "avg_waste_ratio": "0.08",
                "avg_dish_variety": "16.0",
                "latest_compliance_rate": "0.75",
            }
        if path == "dashboard/trends":
            return {
                "points": [
                    {
                        "date": f"2026-09-{index + 1:02d}",
                        "diner_count": 1800,
                        "oil_per_capita_g": "16.0",
                        "salt_per_capita_g": "4.5",
                        "sugar_per_capita_g": "5.0",
                    }
                    for index in range(20)
                ],
                "targets": [],
            }
        if path == "dashboard/per-capita":
            return {
                "latest_date": "2026-10-17",
                "latest": [{"code": "ENERGY", "label": "能量", "unit": "千卡", "value": "1200"}],
                "average": [{"code": "ENERGY", "label": "能量", "unit": "千卡", "value": "1190"}],
                "comparisons": [
                    {
                        "code": "SALT",
                        "label": "食盐",
                        "unit": "g",
                        "target_min": None,
                        "target_max": "5.000",
                        "actual": "4.50",
                        "status": "ok",
                        "source": "《中国居民膳食指南（2022）》",
                    }
                ],
                "basis_note": "营养与油盐糖口径不同",
            }
        if path == "dashboard/compliance":
            return {
                "overall_rate": "0.7500",
                "points": [
                    {
                        "date": "2026-10-17",
                        "rate": "0.7500",
                        "items": [{"code": "SALT", "actual": "4.50"}],
                    },
                    {
                        "date": "2026-10-18",
                        "rate": "0.0000",
                        "items": [{"code": "SALT", "actual": None}],
                    },
                ],
            }
        if path == "dashboard/waste":
            return {
                "average_ratio": "0.0800",
                "points": [
                    {
                        "date": "2026-10-17",
                        "produced_weight_g": "1000",
                        "leftover_weight_g": "80",
                        "waste_ratio": "0.0800",
                    }
                ],
            }
        if path == f"collection/logs/{TODAY}":
            return {
                "date": str(TODAY),
                "meal_type": "LUNCH",
                "meal_type_label": "午餐",
                "saved": True,
                "submitted_at": "2026-10-18T13:30:00+08:00",
                "diner_count": 400,
                "oil_total_g": "3000",
                "salt_total_g": "900",
                "sugar_total_g": "500",
                "leftover_weight_g": "12000",
                "anomaly_flags": [{"label": "用量对不上"}],
                "menu_confirmed": True,
                "warning": None,
                "dishes": [
                    {
                        "dish_id": DISH_A["id"],
                        "name": DISH_A["name"],
                        "category_label": "半荤",
                        "cooking_method_label": "炒",
                        "selected": True,
                        "servings_produced": "120",
                        "leftover_ratio": "0.05",
                        "energy_kcal": "100",
                        "nutrition_source": "按标准配方推算",
                    },
                    {
                        "dish_id": DISH_B["id"],
                        "name": DISH_B["name"],
                        "category_label": "半荤",
                        "cooking_method_label": "煮",
                        "selected": True,
                        "servings_produced": "200",
                        "leftover_ratio": "0.02",
                        "energy_kcal": "70",
                        "nutrition_source": "按标准配方推算",
                    },
                    {
                        "dish_id": str(uuid4()),
                        "name": "未供应菜",
                        "selected": False,
                        "energy_kcal": None,
                    },
                ],
            }
        if path == "calibration/comparison":
            dish_id = kwargs["params"]["dish_id"]
            if dish_id == DISH_A["id"]:
                return {
                    "theoretical": {
                        "energy_kcal": "100",
                        "protein_g": "8",
                        "fat_g": "6",
                        "carb_g": "3",
                        "sodium_mg": "300",
                    },
                    "calibrated": {
                        "energy_kcal": "105",
                        "protein_g": "8.2",
                        "fat_g": "6.3",
                        "carb_g": "3.1",
                        "sodium_mg": "310",
                    },
                    "sampled": {
                        "energy_kcal": "110",
                        "protein_g": "8.4",
                        "fat_g": "6.6",
                        "carb_g": "3.2",
                        "sodium_mg": "320",
                    },
                }
            return {
                "theoretical": {
                    "energy_kcal": "70",
                    "protein_g": "6",
                    "fat_g": "4",
                    "carb_g": "1",
                    "sodium_mg": "60",
                },
                "calibrated": None,
                "sampled": None,
            }
        if path == "dishes":
            keyword = kwargs["params"].get("keyword", "")
            items = [row for row in (DISH_A, DISH_B) if keyword in row["name"]]
            return {"items": items, "total": len(items)}
        if path == f"dishes/{DISH_A['id']}":
            return {
                **DISH_A,
                "standard_serving_g": "120.00",
                "nutrition": {
                    "date": str(TODAY),
                    "value_type": "THEORETICAL",
                    "energy_kcal": "100",
                    "protein_g": "8",
                    "fat_g": "6",
                    "carb_g": "3",
                    "sodium_mg": "300",
                },
                "recipe": {
                    "ingredients": [
                        {
                            "ingredient_name": "番茄",
                            "quantity_per_serving_g": "80",
                            "edible_ratio_override": None,
                            "unit_price": "5.00",
                        }
                    ],
                    "seasonings": [
                        {
                            "seasoning_name": "食盐",
                            "quantity_per_serving_g": "1.2",
                            "unit_price": "4.00",
                        }
                    ],
                },
            }
        if path == "ingredients":
            return {
                "total": 1,
                "items": [
                    {
                        "id": str(uuid4()),
                        "name": "大白菜",
                        "category_label": "蔬菜类",
                        "energy_kcal": "18.16",
                        "protein_g": "1.5",
                        "fat_g": "0.1",
                        "carb_g": "3.2",
                        "sodium_mg": "57.5",
                        "edible_ratio": "0.87",
                        "unit_price": "1.60",
                        "data_source": "中国食物成分表",
                        "source_version": "大白菜(均值)",
                        "note": "单价为演示值",
                    }
                ],
            }
        if path == "forecast/holidays":
            return {
                "items": [
                    {
                        "date": "2026-10-01",
                        "name": "国庆节放假",
                        "kind": "HOLIDAY",
                        "kind_label": "放假",
                        "is_verified": True,
                        "source_note": "国办发明电〔2025〕7号",
                    },
                    {
                        "date": "2026-10-10",
                        "name": "国庆节调休上班",
                        "kind": "WORKDAY",
                        "kind_label": "调休上班",
                        "is_verified": True,
                        "source_note": "国办发明电〔2025〕7号",
                    },
                    {
                        "date": "2026-11-01",
                        "name": "其他月份",
                        "kind": "HOLIDAY",
                        "kind_label": "放假",
                        "is_verified": True,
                        "source_note": "国办发明电〔2025〕7号",
                    },
                ]
            }
        raise AssertionError(f"Unexpected path {path}")


def make_tools() -> tuple[Tools, BusinessStub]:
    business = BusinessStub()
    conversation = Conversation(
        id=str(uuid4()),
        title="测试",
        created_at="2026-10-18T00:00:00+08:00",
        updated_at="2026-10-18T00:00:00+08:00",
    )
    return (
        Tools(
            business,
            conversation,
            "RECORDER",
            PlanParameters(on_date=TODAY),
        ),
        business,
    )


def test_first_batch_tools_are_registered():
    names = {row["function"]["name"] for row in definitions()}
    assert {
        "get_dashboard",
        "get_menu_day",
        "get_dish_recipe",
        "list_ingredients",
        "list_holidays",
    } <= names


def test_dashboard_returns_trimmed_real_contract():
    tools, _ = make_tools()
    result = asyncio.run(tools.execute("get_dashboard", {"days": 30}))
    assert result["days"] == 30 and result["summary"]["avg_diner_count"] == 1800
    assert len(result["trend"]) == 14 and result["trend_truncated"] is True
    assert result["per_capita"]["comparisons"][0]["actual"] == "4.50"
    assert result["compliance"]["overall_rate_percent"] == "75.0%"
    assert result["compliance"]["last_recorded_date"] == "2026-10-17"


def test_menu_day_prefers_strongest_nutrition_and_skips_unserved_dishes():
    tools, _ = make_tools()
    result = asyncio.run(tools.execute("get_menu_day", {"on_date": str(TODAY)}))
    assert result["selected_count"] == 2
    assert [row["name"] for row in result["dishes"]] == ["番茄炒蛋", "煮鸡蛋"]
    assert result["dishes"][0]["nutrients"]["energy_kcal"] == "110"
    assert result["dishes"][0]["nutrition_basis"] == "抽样实测"
    assert result["dishes"][1]["nutrients"]["energy_kcal"] == "70"
    assert result["dishes"][1]["nutrition_basis"] == "标准配方理论值"
    assert result["anomaly_flags"] == ["用量对不上"]


def test_dish_recipe_resolves_exact_name_and_returns_per_serving_quantities():
    tools, business = make_tools()
    result = asyncio.run(tools.execute("get_dish_recipe", {"keyword": "番茄炒蛋"}))
    assert result["name"] == "番茄炒蛋"
    assert result["ingredients"][0]["quantity_per_serving_g"] == "80"
    assert result["seasonings"][0]["seasoning_name"] == "食盐"
    assert any(path == f"dishes/{DISH_A['id']}" for _, path, _ in business.calls)


def test_ambiguous_dish_name_returns_candidates_without_guessing():
    tools, business = make_tools()
    result = asyncio.run(tools.execute("get_dish_recipe", {"keyword": "蛋"}))
    assert result["ambiguous"] is True
    assert {row["name"] for row in result["candidates"]} == {"番茄炒蛋", "煮鸡蛋"}
    assert not any(path.startswith("dishes/") for _, path, _ in business.calls)


def test_ingredient_and_holiday_queries_keep_units_and_sources():
    tools, _ = make_tools()
    ingredient = asyncio.run(tools.execute("list_ingredients", {"keyword": "大白菜"}))
    assert ingredient["items"][0]["unit_price"] == "1.60"
    assert "元/公斤市品" in ingredient["note"]
    holiday = asyncio.run(tools.execute("list_holidays", {"year": 2026, "month": 10}))
    assert [row["date"] for row in holiday["items"]] == ["2026-10-01", "2026-10-10"]
    assert holiday["source_note"] == "国办发明电〔2025〕7号"

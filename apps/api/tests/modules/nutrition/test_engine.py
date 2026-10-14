"""营养引擎第一层的行为与数值。

这里的期望值全部是**手算**出来的，不是从实现里反抄的：
验收标准要求「随机抽取 5 道菜，系统计算的能量值与称重实测核算值的偏差不超过 15%」，
前提是计算过程本身正确，所以先把每个乘加项核对死。
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from app.modules.nutrition.engine import (
    BASE_TOLERANCE,
    EmptyRecipeError,
    IngredientInput,
    RecipeIngredientLine,
    RecipeSeasoningLine,
    SeasoningInput,
    compute_theoretical_per_capita,
    compute_theoretical_per_serving,
)
from app.shared.enums import CookingMethod, SeasoningCategory


def _ingredient(
    name: str,
    *,
    energy: str | None,
    protein: str | None,
    fat: str | None,
    carb: str | None,
    sodium: str | None,
    edible_ratio: str = "1.0000",
) -> IngredientInput:
    def dec(value: str | None) -> Decimal | None:
        return None if value is None else Decimal(value)

    return IngredientInput(
        id=uuid4(),
        name=name,
        edible_ratio=Decimal(edible_ratio),
        energy_kcal=dec(energy),
        protein_g=dec(protein),
        fat_g=dec(fat),
        carb_g=dec(carb),
        sodium_mg=dec(sodium),
        data_source="测试数据",
        source_version="test",
    )


# 与种子数据里的食材成分一致，便于和三餐搭配互相对照
TOMATO = _ingredient("番茄", energy="20.0", protein="0.9", fat="0.2", carb="4.0", sodium="5.0")
EGG = _ingredient(
    "鸡蛋",
    energy="144.0",
    protein="13.3",
    fat="8.8",
    carb="2.8",
    sodium="131.5",
    edible_ratio="0.8500",
)
RICE = _ingredient("大米", energy="346.0", protein="7.4", fat="0.8", carb="77.9", sodium="3.8")
NORI = _ingredient(
    "紫菜（干）", energy="250.0", protein="26.7", fat="1.1", carb="44.1", sodium="710.3"
)

SOYBEAN_OIL = SeasoningInput(
    id=uuid4(),
    name="大豆油",
    category=SeasoningCategory.EDIBLE_OIL,
    energy_kcal=Decimal("899.0"),
    protein_g=Decimal("0.0"),
    fat_g=Decimal("99.9"),
    carb_g=Decimal("0.0"),
    sodium_mg=Decimal("0.0"),
    data_source="测试数据",
)
SALT = SeasoningInput(
    id=uuid4(),
    name="食盐",
    category=SeasoningCategory.SALT,
    energy_kcal=Decimal("0.0"),
    protein_g=Decimal("0.0"),
    fat_g=Decimal("0.0"),
    carb_g=Decimal("0.0"),
    sodium_mg=Decimal("39311.0"),
    data_source="测试数据",
)
SUGAR = SeasoningInput(
    id=uuid4(),
    name="白砂糖",
    category=SeasoningCategory.SUGAR,
    energy_kcal=Decimal("400.0"),
    protein_g=Decimal("0.0"),
    fat_g=Decimal("0.0"),
    carb_g=Decimal("99.9"),
    sodium_mg=Decimal("0.4"),
    data_source="测试数据",
)


def _recipe(ingredients, seasonings, name="测试菜品", method=CookingMethod.STIR_FRY):
    from app.modules.nutrition.engine import DishRecipe

    return DishRecipe(
        dish_id=uuid4(),
        dish_name=name,
        cooking_method=method,
        recipe_version=1,
        ingredients=tuple(ingredients),
        seasonings=tuple(seasonings),
    )


def test_tomato_egg_matches_hand_calculation() -> None:
    """番茄炒蛋：手算过程写在断言旁边，便于任何人复核。"""
    recipe = _recipe(
        [
            RecipeIngredientLine(TOMATO, Decimal("80.000")),
            RecipeIngredientLine(EGG, Decimal("60.000")),
        ],
        [
            RecipeSeasoningLine(SOYBEAN_OIL, Decimal("6.000")),
            RecipeSeasoningLine(SALT, Decimal("1.200")),
            RecipeSeasoningLine(SUGAR, Decimal("1.500")),
        ],
        name="番茄炒蛋",
    )

    result = compute_theoretical_per_serving(recipe)
    nutrients = result.per_serving

    # 能量：0.8×20 + 0.51×144 + 0.06×899 + 0.015×400
    #     = 16.0 + 73.44 + 53.94 + 6.0
    assert nutrients.energy_kcal == Decimal("149.38")
    # 蛋白质：0.8×0.9 + 0.51×13.3 = 0.72 + 6.783
    assert nutrients.protein_g == Decimal("7.503")
    # 脂肪：0.8×0.2 + 0.51×8.8 + 0.06×99.9 = 0.16 + 4.488 + 5.994
    assert nutrients.fat_g == Decimal("10.642")
    # 碳水：0.8×4.0 + 0.51×2.8 + 0.015×99.9 = 3.2 + 1.428 + 1.4985
    assert nutrients.carb_g == Decimal("6.127")
    # 钠：0.8×5.0 + 0.51×131.5 + 0.012×39311 + 0.015×0.4
    #   = 4.0 + 67.065 + 471.732 + 0.006
    assert nutrients.sodium_mg == Decimal("542.80")


def test_steamed_rice_matches_hand_calculation() -> None:
    """米饭只有一种食材且无调味料，适合校验「可食部比例」是否被正确套用。"""
    recipe = _recipe(
        [RecipeIngredientLine(RICE, Decimal("80.000"))],
        [],
        name="米饭",
        method=CookingMethod.STEAM,
    )

    nutrients = compute_theoretical_per_serving(recipe).per_serving

    assert nutrients.energy_kcal == Decimal("276.80")
    assert nutrients.protein_g == Decimal("5.920")
    assert nutrients.fat_g == Decimal("0.640")
    assert nutrients.carb_g == Decimal("62.320")
    assert nutrients.sodium_mg == Decimal("3.04")


def test_soup_matches_hand_calculation() -> None:
    recipe = _recipe(
        [
            RecipeIngredientLine(NORI, Decimal("3.000")),
            RecipeIngredientLine(EGG, Decimal("15.000")),
        ],
        [
            RecipeSeasoningLine(SALT, Decimal("0.800")),
            RecipeSeasoningLine(SOYBEAN_OIL, Decimal("1.000")),
        ],
        name="紫菜蛋花汤",
        method=CookingMethod.BOIL,
    )

    nutrients = compute_theoretical_per_serving(recipe).per_serving

    # 0.03×250 + 0.1275×144 + 0.01×899
    assert nutrients.energy_kcal == Decimal("34.85")
    # 0.03×26.7 + 0.1275×13.3
    assert nutrients.protein_g == Decimal("2.497")
    # 0.03×1.1 + 0.1275×8.8 + 0.01×99.9
    assert nutrients.fat_g == Decimal("2.154")
    assert nutrients.carb_g == Decimal("1.680")
    # 0.03×710.3 + 0.1275×131.5 + 0.008×39311
    assert nutrients.sodium_mg == Decimal("352.56")


def test_edible_ratio_override_wins_over_ingredient_default() -> None:
    """配方可以覆盖食材库的可食部比例，例如同一种菜在不同做法里处理方式不同。"""
    default_ratio = _recipe([RecipeIngredientLine(EGG, Decimal("100.000"))], [], name="默认可食部")
    overridden = _recipe(
        [RecipeIngredientLine(EGG, Decimal("100.000"), Decimal("1.0000"))],
        [],
        name="覆盖可食部",
    )

    default_energy = compute_theoretical_per_serving(default_ratio).per_serving.energy_kcal
    override_energy = compute_theoretical_per_serving(overridden).per_serving.energy_kcal

    assert default_energy == Decimal("122.40")  # 1.0 × 0.85 × 144
    assert override_energy == Decimal("144.00")  # 1.0 × 1.00 × 144


def test_recipe_without_any_detail_is_rejected() -> None:
    with pytest.raises(EmptyRecipeError):
        compute_theoretical_per_serving(_recipe([], [], name="空配方"))


def test_missing_component_data_is_reported_and_widens_tolerance() -> None:
    """成分缺失必须如实反映，而不是静默按 0 算完还给出同样精确的区间。"""
    partial = _ingredient(
        "缺项食材",
        energy="100.0",
        protein=None,
        fat=None,
        carb=None,
        sodium=None,
    )
    result = compute_theoretical_per_serving(
        _recipe([RecipeIngredientLine(partial, Decimal("100.000"))], [], name="缺项菜品")
    )

    assert result.per_serving.energy_kcal == Decimal("100.00")
    assert result.per_serving.protein_g == Decimal("0.000")
    assert set(result.missing_nutrients) == {"PROTEIN", "FAT", "CARBOHYDRATE", "SODIUM"}

    # 基准区间是 ±15%，缺 4 项时按每项放宽到上限（最多 3 步）→ ±30%
    tolerance = Decimal(result.trace["tolerance"]["applied"])
    assert tolerance == BASE_TOLERANCE + Decimal("0.05") * 3
    assert result.uncertainty["energy_kcal"].upper == Decimal("130.00")


def test_uncertainty_interval_brackets_the_point_value() -> None:
    recipe = _recipe(
        [RecipeIngredientLine(RICE, Decimal("80.000"))], [], name="米饭", method=CookingMethod.STEAM
    )

    result = compute_theoretical_per_serving(recipe)
    interval = result.uncertainty["energy_kcal"]

    # 276.80 × 0.85 / × 1.15
    assert interval.lower == Decimal("235.28")
    assert interval.upper == Decimal("318.32")
    assert result.missing_nutrients == ()


def test_trace_records_recipe_snapshot_for_traceability() -> None:
    """任何营养数值都要能点开看到来源与计算过程。"""
    recipe = _recipe(
        [RecipeIngredientLine(TOMATO, Decimal("80.000"))],
        [RecipeSeasoningLine(SALT, Decimal("1.200"))],
        name="番茄（测试）",
    )

    trace = compute_theoretical_per_serving(recipe).trace

    assert trace["engine"] == "nutrition.theoretical"
    assert trace["layer"] == "标准配方推算"
    assert trace["recipe_version"] == 1
    assert trace["ingredients"][0]["name"] == "番茄"
    assert trace["ingredients"][0]["edible_quantity_g"] == "80.000"
    assert trace["seasonings"][0]["name"] == "食盐"
    assert trace["tolerance"]["base"] == "0.15"


class TestPerCapita:
    """人均口径：当日总营养 ÷ 就餐人次。"""

    def test_uses_consumed_servings_and_diner_count(self) -> None:
        recipe = _recipe(
            [RecipeIngredientLine(RICE, Decimal("80.000"))],
            [],
            name="米饭",
            method=CookingMethod.STEAM,
        )
        per_serving = compute_theoretical_per_serving(recipe).per_serving

        per_capita = compute_theoretical_per_capita(
            per_serving,
            servings_produced=Decimal("500"),
            leftover_ratio=Decimal("0.1000"),
            diner_count=1000,
        )

        # 500 份 × (1 − 0.1) ÷ 1000 人 = 每人 0.45 份 → 276.80 × 0.45
        assert per_capita.energy_kcal == Decimal("124.56")

    def test_leftover_ratio_absent_means_fully_consumed(self) -> None:
        recipe = _recipe([RecipeIngredientLine(RICE, Decimal("80.000"))], [], name="米饭")
        per_serving = compute_theoretical_per_serving(recipe).per_serving

        per_capita = compute_theoretical_per_capita(
            per_serving,
            servings_produced=Decimal("100"),
            leftover_ratio=None,
            diner_count=100,
        )

        assert per_capita.energy_kcal == per_serving.energy_kcal

    def test_zero_diners_is_rejected(self) -> None:
        recipe = _recipe([RecipeIngredientLine(RICE, Decimal("80.000"))], [], name="米饭")
        per_serving = compute_theoretical_per_serving(recipe).per_serving

        with pytest.raises(ValueError, match="就餐人次"):
            compute_theoretical_per_capita(
                per_serving, servings_produced=Decimal("100"), leftover_ratio=None, diner_count=0
            )

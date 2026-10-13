"""五项核心营养指标的字段元数据。

字段名、小数位、单位与营养素代码集中在这一处：引擎、落库、公开大屏与看板都从这里取，
避免单位或精度在不同地方各写一份而对不上。
"""

from __future__ import annotations

from app.shared.enums import NutrientCode

#: 五项核心营养指标，顺序即为展示顺序
NUTRIENT_FIELDS: tuple[str, ...] = (
    "energy_kcal",
    "protein_g",
    "fat_g",
    "carb_g",
    "sodium_mg",
)

#: 落库与展示时的小数位，与数据模型的 Numeric 精度一致
NUTRIENT_SCALES: dict[str, int] = {
    "energy_kcal": 2,
    "protein_g": 3,
    "fat_g": 3,
    "carb_g": 3,
    "sodium_mg": 2,
}

NUTRIENT_UNITS: dict[str, str] = {
    "energy_kcal": "千卡",
    "protein_g": "克",
    "fat_g": "克",
    "carb_g": "克",
    "sodium_mg": "毫克",
}

FIELD_TO_NUTRIENT_CODE: dict[str, NutrientCode] = {
    "energy_kcal": NutrientCode.ENERGY,
    "protein_g": NutrientCode.PROTEIN,
    "fat_g": NutrientCode.FAT,
    "carb_g": NutrientCode.CARBOHYDRATE,
    "sodium_mg": NutrientCode.SODIUM,
}

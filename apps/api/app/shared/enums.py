"""跨业务域共用的枚举词表。

约定：

- 取值一律用稳定的英文大写常量，中文展示名通过 `label` 属性获取。数据库里存的是
  稳定代码，界面上是中文，两边互不干扰，改文案不需要动数据。
- 本模块不依赖 SQLAlchemy，「怎么落库」由 `app/db/types.py` 决定。
"""

from __future__ import annotations

from enum import StrEnum


class LabelledStrEnum(StrEnum):
    """带中文展示名的字符串枚举基类。"""

    @property
    def label(self) -> str:
        return ENUM_LABELS.get(self, self.value)


class UserRole(LabelledStrEnum):
    """登录角色。

    系统中没有学生账号——需求文档里的「学生端」对应的是免登录的公开大屏。
    """

    RECORDER = "RECORDER"
    CANTEEN_ADMIN = "CANTEEN_ADMIN"
    SCHOOL_ADMIN = "SCHOOL_ADMIN"


class MealType(LabelledStrEnum):
    BREAKFAST = "BREAKFAST"
    LUNCH = "LUNCH"
    DINNER = "DINNER"


class DishCategory(LabelledStrEnum):
    MEAT = "MEAT"
    VEGETABLE = "VEGETABLE"
    HALF_MEAT = "HALF_MEAT"
    SOUP = "SOUP"
    STAPLE = "STAPLE"


class CookingMethod(LabelledStrEnum):
    STEAM = "STEAM"
    BOIL = "BOIL"
    STIR_FRY = "STIR_FRY"
    DEEP_FRY = "DEEP_FRY"
    STEW = "STEW"
    COLD_DRESS = "COLD_DRESS"


class IngredientCategory(LabelledStrEnum):
    GRAIN = "GRAIN"
    VEGETABLE = "VEGETABLE"
    FRUIT = "FRUIT"
    LIVESTOCK_POULTRY = "LIVESTOCK_POULTRY"
    AQUATIC = "AQUATIC"
    EGG = "EGG"
    DAIRY = "DAIRY"
    BEAN = "BEAN"
    NUT = "NUT"
    FUNGUS_ALGAE = "FUNGUS_ALGAE"
    OIL_FAT = "OIL_FAT"
    CONDIMENT = "CONDIMENT"
    OTHER = "OTHER"


class SeasoningCategory(LabelledStrEnum):
    EDIBLE_OIL = "EDIBLE_OIL"
    SALT = "SALT"
    SUGAR = "SUGAR"
    SOY_SAUCE = "SOY_SAUCE"
    OYSTER_SAUCE = "OYSTER_SAUCE"
    STARCH = "STARCH"
    OTHER = "OTHER"


class NutrientCode(LabelledStrEnum):
    """五项核心营养指标。"""

    ENERGY = "ENERGY"
    PROTEIN = "PROTEIN"
    FAT = "FAT"
    CARBOHYDRATE = "CARBOHYDRATE"
    SODIUM = "SODIUM"


class NutrientCaliber(LabelledStrEnum):
    """口径维度之一：这个数值说的是「一份菜」还是「一个人」。

    与 `NutritionValueType` 是两个互相独立的维度，禁止混用。
    """

    PER_SERVING = "PER_SERVING"
    PER_CAPITA = "PER_CAPITA"


class NutritionValueType(LabelledStrEnum):
    """口径维度之二：这个数值是怎么来的。

    - THEORETICAL：按标准配方推算
    - CALIBRATED：用当日油盐糖实际用量做了闭环校准
    - SAMPLED：抽样称重实测
    """

    THEORETICAL = "THEORETICAL"
    CALIBRATED = "CALIBRATED"
    SAMPLED = "SAMPLED"


class CalibrationSource(LabelledStrEnum):
    DAILY_CLOSURE = "DAILY_CLOSURE"
    SAMPLING = "SAMPLING"


class FeedbackSource(LabelledStrEnum):
    RECORDER = "RECORDER"
    STUDENT = "STUDENT"


class SuggestionStatus(LabelledStrEnum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class StandardCode(LabelledStrEnum):
    """膳食指南的量化基准项。"""

    ENERGY = "ENERGY"
    PROTEIN = "PROTEIN"
    FAT = "FAT"
    CARBOHYDRATE = "CARBOHYDRATE"
    SODIUM = "SODIUM"
    EDIBLE_OIL = "EDIBLE_OIL"
    ADDED_SUGAR = "ADDED_SUGAR"
    FOOD_VARIETY = "FOOD_VARIETY"


class StandardPeriod(LabelledStrEnum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"


class AuditAction(LabelledStrEnum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    SUBMIT = "SUBMIT"
    APPROVE = "APPROVE"
    REJECT = "REJECT"


# ---------------------------------------------------------------------------
# 中文展示名。集中在一处，便于核对文案；新增取值时必须同步补充。
# ---------------------------------------------------------------------------
ENUM_LABELS: dict[LabelledStrEnum, str] = {
    # 角色
    UserRole.RECORDER: "食堂录入员",
    UserRole.CANTEEN_ADMIN: "食堂管理员",
    UserRole.SCHOOL_ADMIN: "学校管理方",
    # 餐次
    MealType.BREAKFAST: "早餐",
    MealType.LUNCH: "午餐",
    MealType.DINNER: "晚餐",
    # 菜品类别
    DishCategory.MEAT: "荤菜",
    DishCategory.VEGETABLE: "素菜",
    DishCategory.HALF_MEAT: "半荤",
    DishCategory.SOUP: "汤",
    DishCategory.STAPLE: "主食",
    # 烹饪方式
    CookingMethod.STEAM: "蒸",
    CookingMethod.BOIL: "煮",
    CookingMethod.STIR_FRY: "炒",
    CookingMethod.DEEP_FRY: "炸",
    CookingMethod.STEW: "炖",
    CookingMethod.COLD_DRESS: "凉拌",
    # 食材类别
    IngredientCategory.GRAIN: "谷薯类",
    IngredientCategory.VEGETABLE: "蔬菜类",
    IngredientCategory.FRUIT: "水果类",
    IngredientCategory.LIVESTOCK_POULTRY: "畜禽肉类",
    IngredientCategory.AQUATIC: "水产类",
    IngredientCategory.EGG: "蛋类",
    IngredientCategory.DAIRY: "奶类",
    IngredientCategory.BEAN: "豆类",
    IngredientCategory.NUT: "坚果种子类",
    IngredientCategory.FUNGUS_ALGAE: "菌藻类",
    IngredientCategory.OIL_FAT: "油脂类",
    IngredientCategory.CONDIMENT: "调味品",
    IngredientCategory.OTHER: "其他",
    # 调味料类别
    SeasoningCategory.EDIBLE_OIL: "食用油",
    SeasoningCategory.SALT: "食盐",
    SeasoningCategory.SUGAR: "糖",
    SeasoningCategory.SOY_SAUCE: "酱油",
    SeasoningCategory.OYSTER_SAUCE: "蚝油",
    SeasoningCategory.STARCH: "淀粉",
    SeasoningCategory.OTHER: "其他",
    # 营养素
    NutrientCode.ENERGY: "能量",
    NutrientCode.PROTEIN: "蛋白质",
    NutrientCode.FAT: "脂肪",
    NutrientCode.CARBOHYDRATE: "碳水化合物",
    NutrientCode.SODIUM: "钠",
    # 口径
    NutrientCaliber.PER_SERVING: "单份",
    NutrientCaliber.PER_CAPITA: "人均",
    NutritionValueType.THEORETICAL: "理论值",
    NutritionValueType.CALIBRATED: "校准值",
    NutritionValueType.SAMPLED: "抽样实测",
    CalibrationSource.DAILY_CLOSURE: "当日闭环",
    CalibrationSource.SAMPLING: "抽样纠偏",
    # 反馈
    FeedbackSource.RECORDER: "录入员代录",
    FeedbackSource.STUDENT: "学生反馈",
    # 推荐
    SuggestionStatus.PENDING: "待确认",
    SuggestionStatus.ACCEPTED: "已采纳",
    SuggestionStatus.REJECTED: "已否决",
    # 膳食指南基准项
    StandardCode.ENERGY: "能量",
    StandardCode.PROTEIN: "蛋白质",
    StandardCode.FAT: "脂肪",
    StandardCode.CARBOHYDRATE: "碳水化合物",
    StandardCode.SODIUM: "钠",
    StandardCode.EDIBLE_OIL: "食用油",
    StandardCode.ADDED_SUGAR: "添加糖",
    StandardCode.FOOD_VARIETY: "食物种类数",
    StandardPeriod.DAILY: "每日",
    StandardPeriod.WEEKLY: "每周",
    # 留痕动作
    AuditAction.CREATE: "新建",
    AuditAction.UPDATE: "修改",
    AuditAction.DELETE: "删除",
    AuditAction.SUBMIT: "提交",
    AuditAction.APPROVE: "采纳",
    AuditAction.REJECT: "否决",
}

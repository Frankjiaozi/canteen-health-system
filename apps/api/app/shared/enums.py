"""跨业务域共用的枚举词表。

约定：

- 取值一律用稳定的英文大写常量，中文展示名通过 `label` 属性获取。数据库里存的是
  稳定代码，界面上是中文，两边互不干扰，改文案不需要动数据。
- 本模块不依赖 SQLAlchemy，「怎么落库」由 `app/db/types.py` 决定。
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class LabelledStrEnum(StrEnum):
    """带中文展示名的字符串枚举基类。"""

    @property
    def label(self) -> str:
        return ENUM_LABELS.get((type(self), self.value), self.value)


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
    - CALIBRATED：用历史采集的油盐糖实际用量解出系数后做了校准
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


class AnomalyFlag(LabelledStrEnum):
    """采集当天的异常标记。

    它们的作用只有一个：**把这些日子从预测的历史序列里排除**。临时接待让份数虚高，
    停供与设备故障让份数虚低，任何一种进了移动平均都会把预测带偏。

    `CALIBRATION_RESIDUAL` 与另外三个不同：它不由人勾选，而是校准算完之后**系统回写**的——
    当天总量与拟合预测的偏差过大，通常意味着漏记了一道菜或总量抄错，这一天同样不可信。
    """

    RECEPTION = "RECEPTION"
    SUSPENDED = "SUSPENDED"
    EQUIPMENT_FAILURE = "EQUIPMENT_FAILURE"
    CALIBRATION_RESIDUAL = "CALIBRATION_RESIDUAL"


#: 由录入员勾选的异常标记；系统回写的那一个不在其中
MANUAL_ANOMALY_FLAGS: tuple[AnomalyFlag, ...] = (
    AnomalyFlag.RECEPTION,
    AnomalyFlag.SUSPENDED,
    AnomalyFlag.EQUIPMENT_FAILURE,
)


class SuggestionStatus(LabelledStrEnum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class HolidayKind(LabelledStrEnum):
    """日历上的两种日子。

    放假日在校人数骤降、份数要下调；**调休上班的周末反过来按工作日处理**——
    只标放假不标调休，预测会在每个调休周末高估一大截。
    """

    HOLIDAY = "HOLIDAY"
    WORKDAY = "WORKDAY"


class StandardCode(LabelledStrEnum):
    """膳食指南的量化基准项。"""

    ENERGY = "ENERGY"
    PROTEIN = "PROTEIN"
    FAT = "FAT"
    CARBOHYDRATE = "CARBOHYDRATE"
    SODIUM = "SODIUM"
    SALT = "SALT"
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
#
# 键是「枚举类 + 取值」的二元组，而不是单独的取值：StrEnum 之间按值相等，
# 若只用取值作键，`UserRole.RECORDER` 与 `FeedbackSource.RECORDER`、
# `DishCategory.VEGETABLE`（素菜）与 `IngredientCategory.VEGETABLE`（蔬菜类）
# 会互相覆盖，取到另一个枚举的中文文案。
# ---------------------------------------------------------------------------
ENUM_LABELS: dict[tuple[type[LabelledStrEnum], str], str] = {
    # 角色
    (UserRole, UserRole.RECORDER.value): "食堂录入员",
    (UserRole, UserRole.CANTEEN_ADMIN.value): "食堂管理员",
    (UserRole, UserRole.SCHOOL_ADMIN.value): "学校管理方",
    # 餐次
    (MealType, MealType.BREAKFAST.value): "早餐",
    (MealType, MealType.LUNCH.value): "午餐",
    (MealType, MealType.DINNER.value): "晚餐",
    # 菜品类别
    (DishCategory, DishCategory.MEAT.value): "荤菜",
    (DishCategory, DishCategory.VEGETABLE.value): "素菜",
    (DishCategory, DishCategory.HALF_MEAT.value): "半荤",
    (DishCategory, DishCategory.SOUP.value): "汤",
    (DishCategory, DishCategory.STAPLE.value): "主食",
    # 烹饪方式
    (CookingMethod, CookingMethod.STEAM.value): "蒸",
    (CookingMethod, CookingMethod.BOIL.value): "煮",
    (CookingMethod, CookingMethod.STIR_FRY.value): "炒",
    (CookingMethod, CookingMethod.DEEP_FRY.value): "炸",
    (CookingMethod, CookingMethod.STEW.value): "炖",
    (CookingMethod, CookingMethod.COLD_DRESS.value): "凉拌",
    # 食材类别
    (IngredientCategory, IngredientCategory.GRAIN.value): "谷薯类",
    (IngredientCategory, IngredientCategory.VEGETABLE.value): "蔬菜类",
    (IngredientCategory, IngredientCategory.FRUIT.value): "水果类",
    (IngredientCategory, IngredientCategory.LIVESTOCK_POULTRY.value): "畜禽肉类",
    (IngredientCategory, IngredientCategory.AQUATIC.value): "水产类",
    (IngredientCategory, IngredientCategory.EGG.value): "蛋类",
    (IngredientCategory, IngredientCategory.DAIRY.value): "奶类",
    (IngredientCategory, IngredientCategory.BEAN.value): "豆类",
    (IngredientCategory, IngredientCategory.NUT.value): "坚果种子类",
    (IngredientCategory, IngredientCategory.FUNGUS_ALGAE.value): "菌藻类",
    (IngredientCategory, IngredientCategory.OIL_FAT.value): "油脂类",
    (IngredientCategory, IngredientCategory.CONDIMENT.value): "调味品",
    (IngredientCategory, IngredientCategory.OTHER.value): "其他",
    # 调味料类别
    (SeasoningCategory, SeasoningCategory.EDIBLE_OIL.value): "食用油",
    (SeasoningCategory, SeasoningCategory.SALT.value): "食盐",
    (SeasoningCategory, SeasoningCategory.SUGAR.value): "糖",
    (SeasoningCategory, SeasoningCategory.SOY_SAUCE.value): "酱油",
    (SeasoningCategory, SeasoningCategory.OYSTER_SAUCE.value): "蚝油",
    (SeasoningCategory, SeasoningCategory.STARCH.value): "淀粉",
    (SeasoningCategory, SeasoningCategory.OTHER.value): "其他",
    # 营养素
    (NutrientCode, NutrientCode.ENERGY.value): "能量",
    (NutrientCode, NutrientCode.PROTEIN.value): "蛋白质",
    (NutrientCode, NutrientCode.FAT.value): "脂肪",
    (NutrientCode, NutrientCode.CARBOHYDRATE.value): "碳水化合物",
    (NutrientCode, NutrientCode.SODIUM.value): "钠",
    # 口径
    (NutrientCaliber, NutrientCaliber.PER_SERVING.value): "单份",
    (NutrientCaliber, NutrientCaliber.PER_CAPITA.value): "人均",
    (NutritionValueType, NutritionValueType.THEORETICAL.value): "理论值",
    (NutritionValueType, NutritionValueType.CALIBRATED.value): "校准值",
    (NutritionValueType, NutritionValueType.SAMPLED.value): "抽样实测",
    (CalibrationSource, CalibrationSource.DAILY_CLOSURE.value): "当日闭环",
    (CalibrationSource, CalibrationSource.SAMPLING.value): "抽样纠偏",
    # 反馈
    (FeedbackSource, FeedbackSource.RECORDER.value): "录入员代录",
    (FeedbackSource, FeedbackSource.STUDENT.value): "学生反馈",
    # 采集异常标记
    (AnomalyFlag, AnomalyFlag.RECEPTION.value): "临时接待",
    (AnomalyFlag, AnomalyFlag.SUSPENDED.value): "菜品停供",
    (AnomalyFlag, AnomalyFlag.EQUIPMENT_FAILURE.value): "设备故障",
    (AnomalyFlag, AnomalyFlag.CALIBRATION_RESIDUAL.value): "用量对不上（系统判定）",
    # 日历
    (HolidayKind, HolidayKind.HOLIDAY.value): "放假",
    (HolidayKind, HolidayKind.WORKDAY.value): "调休上班",
    # 推荐
    (SuggestionStatus, SuggestionStatus.PENDING.value): "待确认",
    (SuggestionStatus, SuggestionStatus.ACCEPTED.value): "已采纳",
    (SuggestionStatus, SuggestionStatus.REJECTED.value): "已否决",
    # 膳食指南基准项
    (StandardCode, StandardCode.ENERGY.value): "能量",
    (StandardCode, StandardCode.PROTEIN.value): "蛋白质",
    (StandardCode, StandardCode.FAT.value): "脂肪",
    (StandardCode, StandardCode.CARBOHYDRATE.value): "碳水化合物",
    (StandardCode, StandardCode.SODIUM.value): "钠",
    (StandardCode, StandardCode.SALT.value): "食盐",
    (StandardCode, StandardCode.EDIBLE_OIL.value): "食用油",
    (StandardCode, StandardCode.ADDED_SUGAR.value): "添加糖",
    (StandardCode, StandardCode.FOOD_VARIETY.value): "食物种类数",
    (StandardPeriod, StandardPeriod.DAILY.value): "每日",
    (StandardPeriod, StandardPeriod.WEEKLY.value): "每周",
    # 留痕动作
    (AuditAction, AuditAction.CREATE.value): "新建",
    (AuditAction, AuditAction.UPDATE.value): "修改",
    (AuditAction, AuditAction.DELETE.value): "删除",
    (AuditAction, AuditAction.SUBMIT.value): "提交",
    (AuditAction, AuditAction.APPROVE.value): "采纳",
    (AuditAction, AuditAction.REJECT.value): "否决",
}


def resolve_labelled(enum_cls: type[Any], text: str) -> Any | None:
    """按中文文案或稳定代码解析枚举取值，认不出来返回 None。

    批量导入时用得上：填表的人写「蔬菜类」和写「VEGETABLE」都应该认，
    而不是逼着他去查系统内部的代码。
    """
    raw = text.strip()
    if not raw:
        return None
    for member in enum_cls:
        if raw == member.value or raw == member.label:
            return member
    return None

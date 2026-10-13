"""模型注册表。

Alembic 的 autogenerate 与 `Base.metadata` 都依赖「所有模型都已被导入」。
每新增一个业务域，必须在此处导入它的 models，否则生成的迁移会漏表。

本文件是数据层基础设施，是全项目唯一集中引用各域 models 的地方，
因此不受「跨域禁止 import 模型」这条业务代码约束。
"""

from app.db.base import Base
from app.modules.audit.models import AuditLog
from app.modules.auth.models import User
from app.modules.collection.models import DailyLog, DailyLogItem, Feedback
from app.modules.dish.models import Dish, RecipeItem, RecipeSeasoning
from app.modules.forecast.models import Forecast
from app.modules.ingredient.models import Ingredient
from app.modules.menu.models import MenuDay, MenuDayItem
from app.modules.nutrition.models import CalibrationFactor, DishNutrition, NutritionStandard
from app.modules.recommendation.models import MenuSuggestion
from app.modules.seasoning.models import Seasoning

__all__ = [
    "AuditLog",
    "Base",
    "CalibrationFactor",
    "DailyLog",
    "DailyLogItem",
    "Dish",
    "DishNutrition",
    "Feedback",
    "Forecast",
    "Ingredient",
    "MenuDay",
    "MenuDayItem",
    "MenuSuggestion",
    "NutritionStandard",
    "RecipeItem",
    "RecipeSeasoning",
    "Seasoning",
    "User",
]

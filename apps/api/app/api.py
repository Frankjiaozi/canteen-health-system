"""API 路由汇总。

各业务域在 `app/modules/<域>/router.py` 中定义 router，统一在此处挂载；
`app/main.py` 只负责应用装配，不直接引用业务域。
"""

from __future__ import annotations

from fastapi import APIRouter

from app.modules.analytics.router import router as analytics_routes
from app.modules.auth.router import router as auth_routes
from app.modules.collection.router import router as collection_routes
from app.modules.dish.router import router as dish_routes
from app.modules.importer.router import router as import_routes
from app.modules.ingredient.router import router as ingredient_routes
from app.modules.nutrition.router import router as calibration_routes
from app.modules.public.router import router as public_routes
from app.modules.seasoning.router import router as seasoning_routes
from app.modules.system.meta import router as meta_routes
from app.modules.system.router import router as system_routes

# 不挂前缀：容器编排与运维直接访问 /health
root_router = APIRouter()
root_router.include_router(system_routes)

# 业务接口总路由，由 main.py 挂到 /api/v1 下
api_router = APIRouter()
api_router.include_router(auth_routes)
api_router.include_router(meta_routes)
api_router.include_router(ingredient_routes)
api_router.include_router(seasoning_routes)
api_router.include_router(dish_routes)
api_router.include_router(import_routes)
api_router.include_router(collection_routes)
api_router.include_router(public_routes)
api_router.include_router(analytics_routes)
api_router.include_router(calibration_routes)

"""API 路由汇总。

各业务域在 `app/modules/<域>/router.py` 中定义 router，统一在此处挂载；
`app/main.py` 只负责应用装配，不直接引用业务域。
"""

from __future__ import annotations

from fastapi import APIRouter

from app.modules.system.router import router as system_routes

# 不挂前缀：容器编排与运维直接访问 /health
root_router = APIRouter()
root_router.include_router(system_routes)

# 业务接口总路由，由 main.py 挂到 /api/v1 下
api_router = APIRouter()
# 后续模块在此挂载，例如：
# api_router.include_router(ingredient_router)

"""系统域响应模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """存活检查响应。"""

    status: Literal["ok"] = "ok"
    app_name: str = Field(description="应用名称")
    version: str = Field(description="后端版本号")
    env: str = Field(description="运行环境")
    timezone: str = Field(description="业务时区")
    server_time: datetime = Field(description="服务器当前时间（带时区）")


class DatabaseHealthResponse(BaseModel):
    """数据库连通性检查响应。"""

    status: Literal["ok"] = "ok"
    database: Literal["ok"] = "ok"
    server_version: str = Field(description="PostgreSQL 版本")
    latency_ms: float = Field(description="一次往返查询耗时（毫秒）")

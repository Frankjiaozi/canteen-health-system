"""应用配置。

所有配置集中在 `Settings`，通过环境变量或 `apps/api/.env` 覆盖。
业务代码禁止直接读 `os.environ`，一律通过 `get_settings()` 获取。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# apps/api 目录（本文件位于 apps/api/app/core/config.py）
API_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = API_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- 应用 ----
    app_name: str = "食堂健康管理系统"
    app_env: Literal["development", "test", "production"] = "development"
    debug: bool = False
    # 全系统业务日期与时间戳统一使用该时区
    app_timezone: str = "Asia/Shanghai"
    api_prefix: str = "/api/v1"

    # ---- 数据库 ----
    database_url: str = "postgresql+psycopg://canteen:canteen@127.0.0.1:5432/canteen"
    db_echo: bool = False
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # ---- 认证 ----
    jwt_secret: str = "dev-only-secret-please-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480
    cookie_name: str = "canteen_token"
    cookie_secure: bool = False

    # ---- 跨域 ----
    # 开发期前端走 Vite 代理访问后端，同源即可；生产由 nginx 反代，通常留空
    cors_origins: list[str] = []

    @field_validator("app_timezone")
    @classmethod
    def _validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except Exception as exc:
            raise ValueError(f"无效的时区：{value}") from exc
        return value

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.app_timezone)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """进程内单例配置。测试如需覆盖，用 `get_settings.cache_clear()` 重置。"""
    return Settings()

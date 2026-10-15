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
    app_name: str = "知味 · 校园智慧膳食平台"
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
    #: 自助注册开关。演示环境开着（访客可自行注册录入员账号），
    #: 学校内网正式部署时应当关掉，账号一律由管理员开通。
    #: 默认关（fail-closed）：忘了配也不会把写权限敞给拿到网址的人。
    allow_open_registration: bool = False

    # ---- 跨域 ----
    # 开发期前端走 Vite 代理访问后端，同源即可；生产由 nginx 反代，通常留空
    cors_origins: list[str] = []

    # ---- AI 助手 ----
    #: 模型端点，指向任何 OpenAI 兼容的 /chat/completions：
    #: 云端 API 或内网的 vLLM / Ollama 都行，换模型不用改代码。
    #: **留空即「未配置」**：接口返回 503 并说明原因，界面上不给「看起来能用」的假象。
    assistant_base_url: str | None = None
    assistant_api_key: str | None = None
    assistant_model: str | None = None
    assistant_timeout_seconds: float = 60.0
    #: 一次对话最多来回几轮工具调用，防止模型陷在「调工具—再调工具」的循环里。
    #: 取 8 而不是 4：有了 call_api 之后，**试探是正常行为**——先猜路径、被点回来、
    #: 再按参数补一次、可能还要按日期扫几天，4 轮会在答出结论之前就用完（实测踩到）。
    #: 这个上限是「别失控」的保险，不是预算。
    assistant_max_tool_rounds: int = 8
    assistant_temperature: float = 0.2

    # ---- 菜单推荐的营养目标 ----
    #: 全天的能量目标（千卡）。**这是一组演示值，待核实**：
    #: 营养配餐领域常引用《学生餐营养指南》卫生行业标准，但需求文档记录
    #: 「未能核实到权威原文」。结构与数值分开处理——结构（供能比）有指南原文，
    #: 数值先填演示值，界面上标注「待核实」，拿到标准原文后改这里即可。
    nutrition_energy_target_kcal: int = 2000
    #: 全天能量目标的下限；上限由能量目标本身给出
    nutrition_energy_target_min_kcal: int = 1800
    #: 一餐占全天的能量比例：早 30% / 午 40% / 晚 30%
    nutrition_meal_share_lunch: float = 0.4
    #: 一餐的伙食预算（元 / 人）
    nutrition_meal_budget_per_person: float = 8.0

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

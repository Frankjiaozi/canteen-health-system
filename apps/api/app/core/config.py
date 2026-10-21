"""应用配置。

所有配置集中在 `Settings`，通过环境变量或 `apps/api/.env` 覆盖。
业务代码禁止直接读 `os.environ`，一律通过 `get_settings()` 获取。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import field_validator, model_validator
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
    # 菜品图片独立保存，部署时挂载持久卷；不写入配方或营养快照。
    dish_image_dir: Path = API_DIR / "data" / "dish-images"

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

    # ---- 菜单推荐的营养目标 ----
    #: 全天的能量目标（千卡）。**这是一组演示值，待核实**：
    #: 营养配餐领域常引用《学生餐营养指南》卫生行业标准，但需求文档记录
    #: 「未能核实到权威原文」。结构与数值分开处理——结构（供能比）有指南原文，
    #: 数值先填演示值，界面上标注「待核实」，拿到标准原文后改这里即可。
    nutrition_energy_target_kcal: int = 2000
    #: 全天能量目标的下限；上限由能量目标本身给出
    nutrition_energy_target_min_kcal: int = 1800
    #: 各餐占全天的能量比例：早 30% / 午 40% / 晚 30%，三项之和应当为 1。
    #:
    #: 三项分开配，而不是「只配午餐、早晚餐平分剩下的」：后者有两个毛病——
    #: 改午餐比例会连带改掉另外两餐；而且早餐与晚餐天然是同一个数，
    #: 于是两餐的营养目标一字不差（那正是早晚餐菜单算出一样的原因之一）。
    nutrition_meal_share_breakfast: float = 0.3
    nutrition_meal_share_lunch: float = 0.4
    nutrition_meal_share_dinner: float = 0.3
    #: 一餐的伙食预算（元 / 人）
    nutrition_meal_budget_per_person: float = 8.0
    #: A/B 两份标准套餐的就餐人数占比。只影响采购与成本分摊，不影响每份套餐的营养口径。
    #: 两项之和必须为 1；以后接套餐选择预测时，替换这两个比例即可。
    package_share_a: float = 0.5
    package_share_b: float = 0.5

    @field_validator("app_timezone")
    @classmethod
    def _validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except Exception as exc:
            raise ValueError(f"无效的时区：{value}") from exc
        return value

    @model_validator(mode="after")
    def _validate_package_shares(self) -> Settings:
        if self.package_share_a < 0 or self.package_share_b < 0:
            raise ValueError("套餐 A/B 的占比不能为负数")
        if abs(self.package_share_a + self.package_share_b - 1.0) > 1e-9:
            raise ValueError("套餐 A/B 的占比之和必须为 1")
        return self

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

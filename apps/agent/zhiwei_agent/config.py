from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGENT_", env_file=ROOT / ".env", extra="ignore", hide_input_in_errors=True
    )
    business_api_url: str = "http://127.0.0.1:8000/api/v1"
    cookie_name: str = "canteen_token"
    mode: Literal["auto", "rules", "model"] = "auto"
    model_base_url: str = ""
    model_name: str = ""
    model_api_key: SecretStr = SecretStr("")
    data_path: Path = ROOT / "data" / "agent-state.sqlite3"
    data_notice: str = "当前环境数据来源尚未核实，仅用于演示，不代表真实食堂经营结果。"

    @model_validator(mode="after")
    def validate_model(self):
        if self.mode == "model" and not self.model_ready:
            raise ValueError("model 模式需要配置模型地址、名称和密钥")
        if self.model_base_url:
            url = urlsplit(self.model_base_url)
            if not url.hostname or url.username or url.password or url.query or url.fragment:
                raise ValueError("模型基址必须是完整服务地址，不能包含用户凭据、查询参数或片段")
            if url.scheme != "https" and not (
                url.scheme == "http" and url.hostname in {"127.0.0.1", "localhost"}
            ):
                raise ValueError("模型地址必须使用 HTTPS；仅本机开发允许 HTTP")
        return self

    @property
    def model_ready(self) -> bool:
        return bool(
            self.model_base_url and self.model_name and self.model_api_key.get_secret_value()
        )

    @property
    def effective_mode(self) -> str:
        return "model" if self.mode != "rules" and self.model_ready else "rules"


@lru_cache
def get_settings() -> Settings:
    return Settings()

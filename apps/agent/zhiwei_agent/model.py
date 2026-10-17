"""兼容 Chat Completions 的模型适配层，无供应商 SDK 依赖。"""

import httpx

from .config import Settings
from .errors import AgentError
from .tools import definitions


async def complete(settings: Settings, messages: list[dict], transport=None) -> dict:
    try:
        async with httpx.AsyncClient(timeout=35, transport=transport, trust_env=False) as client:
            response = await client.post(
                settings.model_base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": "Bearer " + settings.model_api_key.get_secret_value()},
                json={
                    "model": settings.model_name,
                    "messages": messages,
                    "tools": definitions(),
                    "tool_choice": "auto",
                    "temperature": 0.2,
                    "max_tokens": 1400,
                },
            )
            response.raise_for_status()
            message = response.json()["choices"][0]["message"]
            if not isinstance(message, dict):
                raise ValueError("invalid message")
            return {
                key: value
                for key, value in message.items()
                if key in {"role", "content", "tool_calls"}
            }
    except (httpx.HTTPError, ValueError, KeyError, IndexError) as exc:
        raise AgentError(
            "模型服务暂时不可用。已完成的计算结果会保留；请重试，或由负责人切换规则模式。",
            503,
            "model_unavailable",
        ) from exc

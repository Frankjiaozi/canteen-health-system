"""兼容 Chat Completions 的模型适配层，无供应商 SDK 依赖。"""

import httpx
from pydantic import BaseModel, Field

from .config import Settings
from .errors import AgentError
from .tools import definitions


class ToolFunction(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    arguments: str = Field(max_length=20000)


class ModelToolCall(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    type: str = "function"
    function: ToolFunction


def validate_message(value) -> dict:
    """只保留公开回答和合法工具协议，供应商扩展及隐藏思考不进入循环。"""
    if not isinstance(value, dict):
        raise ValueError("invalid message")
    content, calls = value.get("content"), value.get("tool_calls")
    if content is not None and not isinstance(content, str):
        raise ValueError("invalid content")
    result = {"role": "assistant", "content": content}
    if calls is not None:
        if not isinstance(calls, list) or len(calls) > 4:
            raise ValueError("invalid tool calls")
        parsed = [ModelToolCall.model_validate(call) for call in calls]
        if len({call.id for call in parsed}) != len(parsed) or any(
            call.type != "function" for call in parsed
        ):
            raise ValueError("invalid tool identifiers")
        result["tool_calls"] = [call.model_dump() for call in parsed]
    if "content" not in value:
        result.pop("content")
    return result


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
            return validate_message(response.json()["choices"][0]["message"])
    except httpx.TimeoutException as exc:
        raise AgentError(
            "模型服务响应超时，已完成的结果会保留；请稍后重试。", 503, "model_timeout"
        ) from exc
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise AgentError(
            "模型服务暂时不可用：返回的回答或工具协议无效。已完成的结果会保留，请重试。",
            502,
            "invalid_model_response",
        ) from exc
    except httpx.HTTPError as exc:
        raise AgentError(
            "模型服务暂时不可用。已完成的计算结果会保留；请重试，或由负责人切换规则模式。",
            503,
            "model_unavailable",
        ) from exc

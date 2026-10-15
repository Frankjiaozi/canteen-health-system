"""模型接入：任何 OpenAI 兼容的 `/chat/completions` 都能用。

为什么是「OpenAI 兼容」而不是绑定某一家：需求写明**数据不出校**，正式部署要指向内网的
vLLM / Ollama；演示时想用云端 API 换更好的效果，也只改环境变量。换模型不动代码，
这一层就是为此存在的。

**未配置时不给假象**：`get_chat_provider` 直接抛 503 并说明该怎么配，
界面上显示的也是「还没接模型」，而不是一个点了没反应的输入框。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.core.config import Settings
from app.core.errors import ServiceUnavailableError
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ProviderToolCall:
    """模型要求调用一个工具。"""

    id: str
    name: str
    #: 原始参数字符串（模型给的是 JSON 文本，解析失败要能被发现并回给模型）
    arguments: str


@dataclass(frozen=True, slots=True)
class ProviderReply:
    text: str
    tool_calls: list[ProviderToolCall] = field(default_factory=list)


class ChatProvider(Protocol):
    """模型接入的最小接口。测试里用一个「照着剧本回答」的实现替掉真实网络调用。"""

    name: str

    def complete(
        self, *, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> ProviderReply: ...


class OpenAICompatibleProvider:
    """走 `POST {base_url}/chat/completions` 的实现。"""

    name = "openai-compatible"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        model: str,
        timeout_seconds: float,
        temperature: float,
    ) -> None:
        self.model = model
        self._temperature = temperature
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.Client(headers=headers, timeout=timeout_seconds)

    def complete(
        self, *, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> ProviderReply:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self._temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        try:
            response = self._client.post(self._url, json=payload)
        except httpx.HTTPError as error:
            # 连不上模型是环境问题，说清楚是哪一个地址连不上，别让用户以为是自己问错了
            logger.warning("模型调用失败：%s", error)
            raise ServiceUnavailableError(f"连不上模型服务（{self._url}）：{error}") from error
        if response.status_code >= 400:
            detail = response.text[:300]
            raise ServiceUnavailableError(
                f"模型服务返回 {response.status_code}：{detail}。请核对 ASSISTANT_BASE_URL / "
                "ASSISTANT_API_KEY / ASSISTANT_MODEL 是否配对"
            )
        return _parse_reply(response.json())


def _parse_reply(body: dict[str, Any]) -> ProviderReply:
    """把 OpenAI 格式的响应读成我们要的形状。读不出来就报错，不猜。"""
    choices = body.get("choices") or []
    if not choices:
        raise ServiceUnavailableError("模型没有返回任何结果（choices 为空）")
    message = choices[0].get("message") or {}
    calls = [
        ProviderToolCall(
            id=str(call.get("id") or index),
            name=str((call.get("function") or {}).get("name") or ""),
            arguments=str((call.get("function") or {}).get("arguments") or "{}"),
        )
        for index, call in enumerate(message.get("tool_calls") or [])
    ]
    return ProviderReply(text=str(message.get("content") or ""), tool_calls=calls)


def build_provider(settings: Settings) -> ChatProvider:
    """按配置造一个 provider。缺配置就抛 503，而不是拿默认值硬撑。"""
    if not settings.assistant_base_url or not settings.assistant_model:
        raise ServiceUnavailableError(
            "AI 助手还没有接模型：请配置 ASSISTANT_BASE_URL 与 ASSISTANT_MODEL"
            "（可选 ASSISTANT_API_KEY）。指向内网的 vLLM / Ollama 或云端 OpenAI 兼容端点均可。"
        )
    return OpenAICompatibleProvider(
        base_url=settings.assistant_base_url,
        api_key=settings.assistant_api_key,
        model=settings.assistant_model,
        timeout_seconds=settings.assistant_timeout_seconds,
        temperature=settings.assistant_temperature,
    )


def parse_arguments(raw: str) -> dict[str, Any]:
    """解析模型给的参数。解析不了返回空字典并由调用方把错误回给模型，让它重试。"""
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}

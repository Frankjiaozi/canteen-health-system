"""模型接入：任何 OpenAI 兼容的 `/chat/completions` 都能用。

为什么是「OpenAI 兼容」而不是绑定某一家：云端 API 与校内自部署的 vLLM / Ollama
在协议上是一回事，换模型只改环境变量、不动代码——这一层就是为此存在的。

**数据流向要如实交代**：助手会把查出来的菜品级数据（菜名、营养、成本、指标）
随请求发给所配置的模型服务方。选云端就意味着这些内容出校；不需要助手时把
`ASSISTANT_BASE_URL` 留空即为关闭。这是部署方的选择，但必须写在明处。

**未配置时不给假象**：`get_chat_provider` 直接抛 503 并说明该怎么配，
界面上显示的也是「还没接模型」，而不是一个点了没反应的输入框。
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
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


@dataclass(frozen=True, slots=True)
class StreamChunk:
    """流式返回的一小步。

    `text` 是这一段新增的文字；`reply` 只在**最后**一块上给（那时工具调用才拼全）。
    """

    text: str = ""
    reply: ProviderReply | None = None


class ChatProvider(Protocol):
    """模型接入的最小接口。测试里用一个「照着剧本回答」的实现替掉真实网络调用。"""

    name: str

    def complete(
        self, *, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> ProviderReply: ...

    def stream(
        self, *, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> Iterator[StreamChunk]: ...


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

    def stream(
        self, *, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> Iterator[StreamChunk]:
        """按 SSE 读增量。工具调用的参数是**碎片**，必须自己攒起来。"""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self._temperature,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        accumulator = ToolCallAccumulator()
        text_parts: list[str] = []
        try:
            with self._client.stream("POST", self._url, json=payload) as response:
                if response.status_code >= 400:
                    detail = response.read().decode("utf-8", "ignore")[:300]
                    raise ServiceUnavailableError(
                        f"模型服务返回 {response.status_code}：{detail}。请核对 "
                        "ASSISTANT_BASE_URL / ASSISTANT_API_KEY / ASSISTANT_MODEL 是否配对"
                    )
                for event in iter_sse_data(response.iter_lines()):
                    delta = _first_delta(event)
                    if delta is None:
                        continue
                    piece = delta.get("content")
                    if piece:
                        text_parts.append(str(piece))
                        yield StreamChunk(text=str(piece))
                    calls = delta.get("tool_calls")
                    if calls:
                        accumulator.feed(calls)
        except httpx.HTTPError as error:
            logger.warning("模型流式调用失败：%s", error)
            raise ServiceUnavailableError(f"连不上模型服务（{self._url}）：{error}") from error

        yield StreamChunk(
            reply=ProviderReply(text="".join(text_parts), tool_calls=accumulator.result())
        )


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


def iter_sse_data(lines: Iterable[str]) -> Iterator[dict[str, Any]]:
    """从 SSE 行里取出 data 载荷。

    认不出来的行直接跳过（注释行、心跳、半截的 JSON）：一条坏块不该让整轮对话断掉，
    模型那边偶尔会发出空行或非 JSON 的片段。
    """
    for line in lines:
        entry = line.strip()
        if not entry or entry.startswith(":") or not entry.startswith("data:"):
            continue
        payload = entry[len("data:") :].strip()
        if payload == "[DONE]":
            return
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            yield parsed


def _first_delta(event: dict[str, Any]) -> dict[str, Any] | None:
    choices = event.get("choices") or []
    if not choices:
        return None
    delta = choices[0].get("delta")
    return delta if isinstance(delta, dict) else None


class ToolCallAccumulator:
    """把流式返回的工具调用碎片拼回完整的调用。

    OpenAI 兼容协议里，工具调用是**分片**送来的：第一片带 id 与函数名，
    参数按字符陆续到达（`{"days"` / `: 7}`）。不攒起来就会拿到半个 JSON，
    而半个 JSON 只会让工具以「参数为空」的方式静默跑错。
    """

    def __init__(self) -> None:
        self._parts: dict[int, dict[str, str]] = {}

    def feed(self, calls: list[dict[str, Any]]) -> None:
        for position, call in enumerate(calls):
            index = int(call.get("index", position))
            entry = self._parts.setdefault(index, {"id": "", "name": "", "arguments": ""})
            if call.get("id"):
                entry["id"] = str(call["id"])
            function = call.get("function") or {}
            if function.get("name"):
                entry["name"] = str(function["name"])
            if function.get("arguments"):
                entry["arguments"] += str(function["arguments"])

    def result(self) -> list[ProviderToolCall]:
        return [
            ProviderToolCall(
                id=entry["id"] or f"call-{index}",
                name=entry["name"],
                arguments=entry["arguments"] or "{}",
            )
            for index, entry in sorted(self._parts.items())
        ]


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

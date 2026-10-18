"""所有业务能力只走固定路径的 HTTP；浏览器凭据只转发给业务服务。"""

from typing import Any

import httpx

from .errors import AgentError


class BusinessClient:
    def __init__(self, base_url: str, cookie_name: str, token: str, transport=None):
        self.client = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/",
            cookies={cookie_name: token},
            timeout=40,
            transport=transport,
            trust_env=False,
        )

    async def close(self):
        await self.client.aclose()

    async def request(self, method: str, path: str, **kwargs) -> Any:
        try:
            response = await self.client.request(method, path.lstrip("/"), **kwargs)
        except httpx.RequestError as exc:
            raise AgentError(
                "业务服务暂时无法连接，请检查后端和数据库是否运行", 503, "business_unavailable"
            ) from exc
        if response.is_error:
            try:
                body = response.json()
            except ValueError:
                body = {}
            raise AgentError(
                body.get("message", "业务操作失败，请重试"),
                response.status_code,
                body.get("code", "business_error"),
                body.get("details"),
            )
        try:
            return response.json()
        except ValueError as exc:
            raise AgentError("业务服务响应格式不正确", 502, "invalid_business_response") from exc

    async def current_user(self) -> dict:
        return await self.request("GET", "auth/me")

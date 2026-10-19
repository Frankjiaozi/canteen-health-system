"""所有业务能力只走固定路径的 HTTP；浏览器凭据只转发给业务服务。"""

from typing import Any
from urllib.parse import unquote, urlsplit

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
        parsed = urlsplit(path)
        decoded = unquote(path)
        if (
            not path
            or parsed.scheme
            or parsed.netloc
            or parsed.query
            or parsed.fragment
            or decoded.startswith("/")
            or "\\" in decoded
            or any(part in {".", ".."} for part in decoded.split("/"))
        ):
            raise AgentError("业务接口路径必须位于固定 API 地址下", 422, "invalid_business_path")
        try:
            response = await self.client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise AgentError(
                "业务服务响应超时，已完成的结果保留，请稍后重试", 503, "business_timeout"
            ) from exc
        except httpx.RequestError as exc:
            raise AgentError(
                "业务服务暂时无法连接，请检查后端和数据库是否运行", 503, "business_unavailable"
            ) from exc
        if response.is_error:
            try:
                body = response.json()
            except ValueError:
                body = {}
            if not isinstance(body, dict):
                body = {}
            detail = body.get("detail")
            message = body.get("message")
            if not isinstance(message, str) or not message:
                message = (
                    detail
                    if isinstance(detail, str)
                    else (
                        "业务请求参数有误，请核对字段"
                        if isinstance(detail, list)
                        else "业务操作失败，请重试"
                    )
                )
            details = body.get("details")
            if details is None and isinstance(detail, list):
                # 不转发 Pydantic 的 input/ctx（可能包含用户凭据或内部对象）。
                details = [
                    {
                        "field": ".".join(map(str, item.get("loc", []))),
                        "message": item.get("msg", "参数有误"),
                    }
                    for item in detail
                    if isinstance(item, dict)
                ]
            raise AgentError(
                message,
                response.status_code,
                body.get("code", "business_error"),
                details,
            )
        try:
            return response.json()
        except ValueError as exc:
            raise AgentError("业务服务响应格式不正确", 502, "invalid_business_response") from exc

    async def current_user(self) -> dict:
        user = await self.request("GET", "auth/me")
        if (
            not isinstance(user, dict)
            or not isinstance(user.get("id"), str)
            or not user["id"]
            or user.get("role") not in {"RECORDER", "CANTEEN_ADMIN", "SCHOOL_ADMIN"}
        ):
            raise AgentError(
                "业务登录态响应不符合接口契约，请重新登录或检查业务服务", 502, "contract_mismatch"
            )
        return user

"""人工运行的真实模型工具协议冒烟；不调用业务 API、不发布、不输出供应商原文。"""

import argparse
import asyncio
import json

from .config import Settings
from .errors import AgentError
from .model import complete
from .schemas import DishArguments


async def check_model(settings: Settings, transport=None) -> dict:
    if settings.effective_mode != "model":
        raise AgentError("当前未启用真实模型，请先配置 AGENT_MODEL_*", 422, "model_not_configured")
    response = await complete(
        settings,
        [
            {
                "role": "system",
                "content": "这是工具协议检查。请只调用一次 list_dishes，keyword 为空字符串，不回答业务数字。",
            },
            {"role": "user", "content": "请调用菜品查询工具，检查空关键词请求。"},
        ],
        transport,
    )
    calls = response.get("tool_calls") or []
    try:
        if len(calls) != 1 or calls[0]["function"]["name"] != "list_dishes":
            raise ValueError("expected list_dishes")
        arguments = DishArguments.model_validate_json(calls[0]["function"]["arguments"])
        if arguments.keyword != "":
            raise ValueError("expected empty keyword")
    except (ValueError, KeyError, TypeError) as exc:
        raise AgentError(
            "模型未返回预期的菜品查询工具调用；请核对该模型的 tools 支持", 502, "smoke_failed"
        ) from exc
    return {"status": "ok", "check": "model_tool_protocol", "business_executed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="明确执行一次可能计费的真实模型请求")
    args = parser.parse_args()
    if not args.run:
        parser.error("仅人工验收时添加 --run；默认不联网")
    try:
        result = asyncio.run(check_model(Settings()))
    except (AgentError, ValueError) as exc:
        result = {
            "status": "failed",
            "code": exc.code if isinstance(exc, AgentError) else "invalid_config",
        }
        print(json.dumps(result, ensure_ascii=False))
        raise SystemExit(1) from None
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

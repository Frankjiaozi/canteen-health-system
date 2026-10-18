import asyncio
import json

import httpx
import pytest

from zhiwei_agent.config import Settings
from zhiwei_agent.errors import AgentError
from zhiwei_agent.model import complete


def settings(tmp_path):
    return Settings(
        data_path=tmp_path / "adapter.sqlite3",
        mode="model",
        model_base_url="https://model.invalid/v1",
        model_name="compatible-tools-model",
        model_api_key="private-test-key",
        _env_file=None,
    )


def test_wire_protocol_sends_tools_without_business_cookie_or_exposing_reasoning(tmp_path):
    history = [{"role": "user", "content": "核查近期记录"}]

    def handler(request):
        assert str(request.url) == "https://model.invalid/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer private-test-key"
        assert "cookie" not in request.headers
        body = json.loads(request.content)
        assert body["messages"] == history
        assert {item["function"]["name"] for item in body["tools"]} == {
            "generate_menu_plan",
            "review_operations",
            "list_dishes",
            "get_current_plan",
            "check_data_readiness",
            "clarify_task",
        }
        assert all(
            item["function"]["parameters"]["additionalProperties"] is False
            for item in body["tools"]
        )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "已核查",
                            "reasoning_content": "不应返回的推理",
                        }
                    }
                ]
            },
        )

    result = asyncio.run(complete(settings(tmp_path), history, httpx.MockTransport(handler)))
    assert result == {"role": "assistant", "content": "已核查"}


def test_provider_error_does_not_echo_secret_or_provider_body(tmp_path):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(401, json={"error": "private-test-key provider debug"})
    )
    with pytest.raises(AgentError) as caught:
        asyncio.run(complete(settings(tmp_path), [], transport))
    assert caught.value.code == "model_unavailable"
    assert "private-test-key" not in json.dumps(caught.value.body())


def test_malformed_provider_response_is_reported_as_unavailable(tmp_path):
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"choices": []}))
    with pytest.raises(AgentError, match="模型服务暂时不可用"):
        asyncio.run(complete(settings(tmp_path), [], transport))


def test_incomplete_explicit_model_config_does_not_start(tmp_path):
    with pytest.raises(ValueError) as caught:
        Settings(
            data_path=tmp_path / "missing.sqlite3",
            mode="model",
            model_api_key="private-test-key",
            _env_file=None,
        )
    assert "private-test-key" not in str(caught.value)

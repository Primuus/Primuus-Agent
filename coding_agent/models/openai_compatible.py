"""Chat Completions backend for OpenAI-compatible model endpoints."""

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from coding_agent.contracts import ModelResponse, ToolCall
from coding_agent.models.base import ModelServiceError


class OpenAICompatibleBackend:
    def __init__(
        self,
        model_id: str,
        base_url: str,
        api_key: str | None,
        timeout_seconds: int = 120,
    ) -> None:
        self.model_id = model_id
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def generate(
        self, messages: list[dict[str, Any]], tools: list[dict]
    ) -> ModelResponse:
        payload = {
            "model": self.model_id,
            "messages": messages,
            "tools": [
                {"type": "function", "function": tool}
                for tool in tools
            ],
            "parallel_tool_calls": False,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                completion = json.load(response)
        except HTTPError as error:
            raise ModelServiceError(f"Model API returned HTTP {error.code}") from error
        except URLError as error:
            raise ModelServiceError(str(error.reason)) from error
        except TimeoutError as error:
            raise ModelServiceError("Model API request timed out") from error

        message = completion["choices"][0]["message"]
        usage = completion.get("usage") or {}
        calls = message.get("tool_calls") or []
        if calls:
            if len(calls) != 1:
                raise ValueError("Expected exactly one tool call")
            function = calls[0]["function"]
            return ModelResponse(
                tool_call=ToolCall(
                    call_id=calls[0].get("id") or uuid4().hex,
                    name=function["name"],
                    arguments=json.loads(function["arguments"]),
                ),
                input_tokens=usage.get("prompt_tokens"),
                output_tokens=usage.get("completion_tokens"),
            )
        return ModelResponse(
            final_message=message.get("content"),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
        )

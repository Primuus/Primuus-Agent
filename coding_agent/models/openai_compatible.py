"""Chat Completions backend for OpenAI-compatible model endpoints."""

import json
from http.client import IncompleteRead
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
        max_output_tokens: int = 8192,
        reasoning_effort: str | None = None,
        final_reasoning_effort: str | None = None,
    ) -> None:
        self.model_id = model_id
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens
        self.reasoning_effort = reasoning_effort
        self.final_reasoning_effort = final_reasoning_effort

    def generate(
        self, messages: list[dict[str, Any]], tools: list[dict],
        *, max_output_tokens: int | None = None,
    ) -> ModelResponse:
        payload = {
            "model": self.model_id,
            "messages": messages,
            "max_tokens": min(self.max_output_tokens, max_output_tokens or self.max_output_tokens),
        }
        if tools:
            payload["tools"] = [
                {"type": "function", "function": tool}
                for tool in tools
            ]
            payload["parallel_tool_calls"] = False
        effort = self.final_reasoning_effort if not tools and self.final_reasoning_effort is not None else self.reasoning_effort
        if effort is not None:
            payload["reasoning_effort"] = effort
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                completion = json.load(response)
        except HTTPError as error:
            detail = error.read(2048).decode("utf-8", errors="replace").strip()
            if self.api_key:
                detail = detail.replace(self.api_key, "[redacted]")
            raise ModelServiceError(
                f"Model API returned HTTP {error.code}: {detail}",
                retryable=error.code in (408, 429, 500, 502, 503, 504),
            ) from error
        except URLError as error:
            raise ModelServiceError(str(error.reason), retryable=True) from error
        except TimeoutError as error:
            raise ModelServiceError("Model API request timed out", retryable=True) from error
        except IncompleteRead as error:
            raise ModelServiceError("Model API response was truncated", retryable=True) from error

        message = completion["choices"][0]["message"]
        reasoning = message.get("reasoning_content")
        if effort == "none" and reasoning is None:
            reasoning = ""
        usage = completion.get("usage") or {}
        if completion["choices"][0]["finish_reason"] == "length":
            raise ModelServiceError(
                "Model response reached the configured output limit", retryable=False,
                input_tokens=usage.get("prompt_tokens"), output_tokens=usage.get("completion_tokens"),
            )
        calls = message.get("tool_calls") or []
        if calls:
            return ModelResponse(
                tool_calls=tuple(
                    ToolCall(
                        call_id=call.get("id") or uuid4().hex,
                        name=call["function"]["name"],
                        arguments=json.loads(call["function"]["arguments"]),
                    )
                    for call in calls
                ),
                input_tokens=usage.get("prompt_tokens"),
                output_tokens=usage.get("completion_tokens"),
                reasoning_content=reasoning,
                assistant_content=message.get("content"),
            )
        return ModelResponse(
            final_message=message.get("content"),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            reasoning_content=reasoning,
        )

"""Anthropic Messages adapter for the shared model contract."""

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from coding_agent.contracts import ModelResponse, ToolCall
from coding_agent.models.base import ModelServiceError


class AnthropicBackend:
    def __init__(
        self, model_id: str, base_url: str, api_key: str | None,
        max_output_tokens: int = 4096, timeout_seconds: int = 120,
    ) -> None:
        self.model_id = model_id
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.max_output_tokens = max_output_tokens
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _conversation(messages: list[dict[str, Any]]) -> tuple[str, list[dict]]:
        system = []
        conversation: list[dict] = []
        for message in messages:
            role = message["role"]
            if role == "system":
                system.append(message["content"])
                continue
            if role == "assistant":
                if message.get("tool_calls"):
                    content = ([{"type": "text", "text": message["content"]}]
                               if message.get("content") else []) + [{
                        "type": "tool_use", "id": call["id"],
                        "name": call["function"]["name"],
                        "input": json.loads(call["function"]["arguments"]),
                    } for call in message["tool_calls"]]
                else:
                    content = [{"type": "text", "text": message["content"]}]
            elif role == "tool":
                role = "user"
                content = [{
                    "type": "tool_result", "tool_use_id": message["tool_call_id"],
                    "content": message["content"],
                }]
            else:
                content = [{"type": "text", "text": message["content"]}]
            if conversation and conversation[-1]["role"] == role:
                conversation[-1]["content"].extend(content)
            else:
                conversation.append({"role": role, "content": content})
        if conversation and conversation[-1]["role"] == "assistant":
            conversation.append({
                "role": "user",
                "content": [{"type": "text", "text": "Continue the task using the latest instructions."}],
            })
        return "\n\n".join(system), conversation

    def generate(
        self, messages: list[dict[str, Any]], tools: list[dict],
        *, max_output_tokens: int | None = None,
    ) -> ModelResponse:
        system, conversation = self._conversation(messages)
        payload = {
            "model": self.model_id,
            "max_tokens": min(self.max_output_tokens, max_output_tokens or self.max_output_tokens),
            "system": system,
            "messages": conversation,
        }
        if tools:
            payload["tools"] = [{
                "name": tool["name"],
                "description": tool["description"],
                "input_schema": tool["parameters"],
            } for tool in tools]
        request = Request(
            f"{self.base_url}/v1/messages",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01",
                "x-api-key": self.api_key or "",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                completion = json.load(response)
        except HTTPError as error:
            raise ModelServiceError(
                f"Model API returned HTTP {error.code}",
                retryable=error.code in (408, 429, 500, 502, 503, 504),
            ) from error
        except URLError as error:
            raise ModelServiceError(str(error.reason), retryable=True) from error
        except TimeoutError as error:
            raise ModelServiceError("Model API request timed out", retryable=True) from error

        usage = completion.get("usage") or {}
        if completion["stop_reason"] == "max_tokens":
            raise ModelServiceError(
                "Model response reached the configured output limit", retryable=False,
                input_tokens=usage.get("input_tokens"), output_tokens=usage.get("output_tokens"),
            )
        calls = [block for block in completion["content"] if block["type"] == "tool_use"]
        text = "\n".join(block["text"] for block in completion["content"] if block["type"] == "text")
        if calls:
            return ModelResponse(
                tool_calls=tuple(ToolCall(block["id"], block["name"], block["input"]) for block in calls),
                input_tokens=usage.get("input_tokens"),
                output_tokens=usage.get("output_tokens"),
                assistant_content=text or None,
            )
        return ModelResponse(
            final_message=text,
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
        )

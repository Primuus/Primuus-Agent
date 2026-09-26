"""Deterministic backend for exercising the agent loop."""

from coding_agent.contracts import ModelResponse
from typing import Any


class ScriptedBackend:
    model_id = "scripted"

    def __init__(self, responses: list[ModelResponse]) -> None:
        self.responses = iter(responses)

    def generate(
        self, messages: list[dict[str, Any]], tools: list[dict]
    ) -> ModelResponse:
        return next(self.responses)

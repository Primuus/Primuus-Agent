"""Model backend interface."""

from typing import Protocol

from coding_agent.contracts import ModelResponse


class ModelBackend(Protocol):
    model_id: str

    def generate(
        self, messages: list[dict[str, str]], tools: list[dict]
    ) -> ModelResponse: ...

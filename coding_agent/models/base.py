"""Model backend interface."""

from typing import Any, Protocol

from coding_agent.contracts import ModelResponse


class ModelBackend(Protocol):
    model_id: str

    def generate(
        self, messages: list[dict[str, Any]], tools: list[dict]
    ) -> ModelResponse: ...


class ModelServiceError(Exception):
    """The configured model endpoint could not complete a request."""

    def __init__(self, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable

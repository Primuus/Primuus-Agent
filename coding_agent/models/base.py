"""Model backend interface."""

from typing import Any, Protocol

from coding_agent.contracts import ModelResponse


class ModelBackend(Protocol):
    model_id: str

    def generate(
        self, messages: list[dict[str, Any]], tools: list[dict],
        *, max_output_tokens: int | None = None,
    ) -> ModelResponse: ...


class ModelServiceError(Exception):
    """The configured model endpoint could not complete a request."""

    def __init__(self, message: str, retryable: bool = False,
                 input_tokens: int | None = None, output_tokens: int | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens

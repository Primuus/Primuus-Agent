"""Shared data contracts for the first-stage agent pipeline.

Loading tasks, executing actions, and writing results live in their respective
modules.
"""

from dataclasses import dataclass
from typing import Any, Literal


ToolStatus = Literal["completed", "error", "timeout"]
StopReason = Literal[
    "verified",
    "completed",
    "paused",
    "token_budget",
    "final_unverified",
    "max_steps",
    "timeout",
    "invalid_model_action",
    "model_error",
    "tool_error",
    "verifier_error",
    "recovery_exhausted",
]


@dataclass(frozen=True)
class VerifierSpec:
    kind: str
    entrypoint: str


@dataclass(frozen=True)
class TaskSpec:
    schema_version: int
    task_id: str
    title: str
    tags: list[str]
    verifier: VerifierSpec


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ModelResponse:
    """One or more tool calls, or one final message per model turn."""

    tool_calls: tuple[ToolCall, ...] = ()
    final_message: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_content: str | None = None
    assistant_content: str | None = None

    def __post_init__(self) -> None:
        if bool(self.tool_calls) == (self.final_message is not None):
            raise ValueError("A model response must have tool calls or one final message")
        if self.final_message is not None and not self.final_message.strip():
            raise ValueError("A final message cannot be empty")


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    name: str
    status: ToolStatus
    output: str
    error: str | None
    exit_code: int | None
    duration_ms: int


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    output: str
    error: str | None
    exit_code: int
    duration_ms: int


@dataclass(frozen=True)
class RunResult:
    run_id: str
    task_id: str
    model_id: str
    success: bool
    stop_reason: StopReason
    steps: int
    tool_calls: int
    failed_tool_calls: int
    retries: int
    recoveries: int
    manual_interventions: int
    failure_counts: dict[str, int]
    tokens: int | None
    latency_seconds: float
    trace_path: str

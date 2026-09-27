"""Failure categories and bounded recovery settings for a session."""

from dataclasses import dataclass
import hashlib
import json
import re

from coding_agent.contracts import ToolCall, ToolResult


@dataclass(frozen=True)
class RecoveryPolicy:
    enabled: bool = False
    model_retries: int = 2
    tool_retries: int = 1
    validation_retries: int = 1
    repeat_blocks: int = 2

    @classmethod
    def from_config(cls, config: dict) -> "RecoveryPolicy":
        settings = config.get("recovery", {})
        return cls(**settings)


def action_signature(call: ToolCall) -> str:
    action = json.dumps(
        {"name": call.name, "arguments": call.arguments},
        ensure_ascii=False, sort_keys=True,
    )
    return hashlib.sha256(action.encode("utf-8")).hexdigest()


def failure_category(call: ToolCall, result: ToolResult) -> str | None:
    if result.status == "completed" and result.exit_code in (None, 0):
        return None
    if result.error in ("Action denied by read-only mode", "Action declined"):
        return "permission"
    if result.status == "error" and result.exit_code is None:
        return "tool"
    if call.name != "run_shell":
        return "tool"
    command = call.arguments.get("command")
    if not isinstance(command, str):
        return "tool"
    command = command.lower()
    if re.search(r"\b(pytest|unittest|ctest)\b|\b(?:npm|pnpm|yarn|cargo|go)\s+(?:run\s+)?test\b", command):
        return "test"
    if re.search(r"\b(build|compile|compileall|py_compile|cmake|make|mvn|gradle|tsc)\b|\bcargo\s+check\b", command):
        return "build"
    return "command"


def alternative_guidance(category: str, call: ToolCall) -> str:
    if category == "permission":
        return "The action was not permitted. Continue with allowed actions or ask the user for permission."
    if category == "tool":
        return f"{call.name} failed. Inspect the target file or arguments before choosing a different edit."
    if category in ("build", "test"):
        return f"The {category} command failed. Inspect its output and related source, then change the code before rerunning it."
    return "The command failed. Inspect its output and workspace state before choosing another action."

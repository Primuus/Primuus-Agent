"""State and event contracts shared by interactive sessions and evaluation."""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from typing import Any, Callable

from coding_agent.contracts import ModelResponse, StopReason, ToolResult, VerificationResult


@dataclass(frozen=True)
class SessionSpec:
    session_id: str
    instructions: str


@dataclass
class Turn:
    response: ModelResponse
    model_at: str
    model_duration_ms: int
    observations: list[tuple[ToolResult, str]] = field(default_factory=list)
    verification: VerificationResult | None = None
    verification_at: str | None = None


@dataclass
class SessionState:
    session_id: str
    steps: int = 0
    turns: list[Turn] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    stop_reason: StopReason | None = None
    tokens: int | None = 0
    event_sink: Callable[[dict[str, Any]], None] | None = field(default=None, repr=False)

    @property
    def success(self) -> bool:
        return self.stop_reason in ("verified", "completed")

    @property
    def tool_calls(self) -> int:
        return sum(len(turn.response.tool_calls) for turn in self.turns)

    @property
    def failed_tool_calls(self) -> int:
        return sum(
            result.status != "completed" or result.exit_code not in (None, 0)
            for turn in self.turns
            for result, _ in turn.observations
        )

    def emit(self, event_type: str, data: dict[str, Any], step: int | None = None) -> str:
        timestamp = datetime.now(timezone.utc).isoformat()
        event = {
            "run_id": self.session_id,
            "step": self.steps if step is None else step,
            "event_type": event_type,
            "timestamp": timestamp,
            "data": data,
        }
        if self.event_sink is not None:
            self.event_sink(event)
        self.events.append(event)
        return timestamp

    def add_user_message(self, content: str) -> None:
        self.emit("user_message", {"content": content})
        self.messages.append({"role": "user", "content": content})
        self.stop_reason = None

    def add_turn(self, response: ModelResponse, model_duration_ms: int) -> Turn:
        step = self.steps + 1
        timestamp = self.emit(
            "model_action",
            {"response": asdict(response), "duration_ms": model_duration_ms},
            step,
        )
        self.steps = step
        turn = Turn(response, timestamp, model_duration_ms)
        self.turns.append(turn)
        if response.input_tokens is None or response.output_tokens is None:
            self.tokens = None
        elif self.tokens is not None:
            self.tokens += response.input_tokens + response.output_tokens
        if response.tool_calls:
            self.messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": call.call_id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments),
                    },
                } for call in response.tool_calls],
            })
        else:
            self.messages.append({"role": "assistant", "content": response.final_message})
        return turn

    def add_observation(self, turn: Turn, result: ToolResult) -> None:
        timestamp = self.emit("tool_result", asdict(result))
        turn.observations.append((result, timestamp))
        self.messages.append({
            "role": "tool",
            "tool_call_id": result.call_id,
            "content": json.dumps(asdict(result)),
        })

    def add_verification(self, turn: Turn, result: VerificationResult) -> None:
        timestamp = self.emit("verification_result", asdict(result))
        turn.verification = result
        turn.verification_at = timestamp

    def finish(self, reason: StopReason) -> None:
        self.emit("task_finished", {"success": reason in ("verified", "completed"), "stop_reason": reason})
        self.stop_reason = reason

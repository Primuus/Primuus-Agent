"""Session state reconstructed from an append-only event journal."""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from typing import Any, Callable

from coding_agent.contracts import ModelResponse, StopReason, ToolCall, ToolResult, VerificationResult


@dataclass(frozen=True)
class SessionSpec:
    session_id: str
    instructions: str | None


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
    plan: list[dict[str, str]] = field(default_factory=list)
    summary: str = ""
    snapshots: list[dict[str, Any]] = field(default_factory=list)
    pending_tools: dict[str, ToolCall] = field(default_factory=dict)
    last_failed_action: str | None = None
    repeat_blocks: int = 0
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

    def _accept_turn(self, response: ModelResponse, duration_ms: int, timestamp: str) -> Turn:
        self.steps += 1
        turn = Turn(response, timestamp, duration_ms)
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
                    "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
                } for call in response.tool_calls],
            })
        else:
            self.messages.append({"role": "assistant", "content": response.final_message})
        return turn

    def add_turn(self, response: ModelResponse, model_duration_ms: int) -> Turn:
        timestamp = self.emit(
            "model_action",
            {"response": asdict(response), "duration_ms": model_duration_ms},
            self.steps + 1,
        )
        return self._accept_turn(response, model_duration_ms, timestamp)

    def start_tool(self, call: ToolCall) -> None:
        self.emit("tool_started", asdict(call))
        self.pending_tools[call.call_id] = call

    def _accept_observation(self, turn: Turn, result: ToolResult, timestamp: str) -> None:
        turn.observations.append((result, timestamp))
        self.messages.append({
            "role": "tool",
            "tool_call_id": result.call_id,
            "content": json.dumps(asdict(result)),
        })
        self.pending_tools.pop(result.call_id, None)

    def add_observation(self, turn: Turn, result: ToolResult) -> None:
        timestamp = self.emit("tool_result", asdict(result))
        self._accept_observation(turn, result, timestamp)

    def add_verification(self, turn: Turn, result: VerificationResult) -> None:
        timestamp = self.emit("verification_result", asdict(result))
        turn.verification = result
        turn.verification_at = timestamp

    def add_guidance(self, content: str) -> None:
        self.emit("recovery_guidance", {"content": content})
        self.messages.append({"role": "system", "content": content})

    def record_failure(self, category: str, detail: dict[str, Any]) -> None:
        self.emit("failure_detected", {"category": category, **detail})
        if "signature" in detail:
            self.last_failed_action = detail["signature"]
            self.repeat_blocks = 0

    def record_repeat_block(self, signature: str, name: str) -> None:
        self.repeat_blocks += 1
        self.emit("recovery_action", {
            "kind": "repeat_block", "signature": signature,
            "name": name, "count": self.repeat_blocks,
        })

    def clear_failed_action(self, kind: str = "alternative_action") -> None:
        if self.last_failed_action is not None:
            self.emit("recovery_action", {"kind": kind})
            self.last_failed_action = None
            self.repeat_blocks = 0

    def update_plan(self, items: list[dict[str, str]]) -> None:
        self.emit("plan_updated", {"items": items})
        self.plan = items

    def add_snapshot(self, commit: str, label: str) -> None:
        snapshot = {"commit": commit, "label": label, "plan": self.plan.copy()}
        self.emit("snapshot_created", snapshot)
        self.snapshots.append(snapshot)

    def record_restore(self, commit: str) -> None:
        self.emit("workspace_restored", {"commit": commit})
        self.messages.append({
            "role": "system",
            "content": f"Workspace restored to snapshot {commit}. Re-inspect files before editing.",
        })

    def compact(self, max_chars: int, keep_messages: int) -> None:
        if len(json.dumps(self.messages, ensure_ascii=False)) <= max_chars:
            return
        start = max(0, len(self.messages) - keep_messages)
        while start > 0 and self.messages[start]["role"] == "tool":
            start -= 1
        if start == 0:
            return
        discarded = self.messages[:start]
        lines = [f"{message['role']}: {str(message.get('content') or message.get('tool_calls'))[:240]}" for message in discarded]
        summary = (self.summary + "\n" + "\n".join(lines)).strip()[-8000:]
        messages = self.messages[start:]
        self.emit("context_compacted", {"summary": summary, "messages": messages})
        self.summary = summary
        self.messages = messages

    def finish(self, reason: StopReason) -> None:
        self.emit("task_finished", {"success": reason in ("verified", "completed"), "stop_reason": reason})
        self.stop_reason = reason

    def resolve_interrupted_turn(self, acknowledge_pending: bool) -> None:
        if self.pending_tools and not acknowledge_pending:
            raise RuntimeError("A tool may have run before interruption; inspect the workspace and use --resolve-pending")
        if not self.turns or not self.turns[-1].response.tool_calls:
            return
        turn = self.turns[-1]
        observed = {result.call_id for result, _ in turn.observations}
        for call in turn.response.tool_calls:
            if call.call_id in observed:
                continue
            detail = "Outcome uncertain after interruption" if call.call_id in self.pending_tools else "Skipped after interruption"
            self.add_observation(turn, ToolResult(call.call_id, call.name, "error", "", detail, None, 0))

    @classmethod
    def from_events(cls, session_id: str, events: list[dict[str, Any]]) -> "SessionState":
        state = cls(session_id)
        for event in events:
            data = event["data"]
            kind = event["event_type"]
            timestamp = event["timestamp"]
            state.events.append(event)
            if kind == "user_message":
                state.messages.append({"role": "user", "content": data["content"]})
                state.stop_reason = None
            elif kind == "model_action":
                raw = data["response"]
                response = ModelResponse(
                    tool_calls=tuple(ToolCall(**call) for call in raw["tool_calls"]),
                    final_message=raw["final_message"],
                    input_tokens=raw["input_tokens"],
                    output_tokens=raw["output_tokens"],
                )
                state._accept_turn(response, data["duration_ms"], timestamp)
            elif kind == "tool_started":
                call = ToolCall(**data)
                state.pending_tools[call.call_id] = call
            elif kind == "tool_result":
                state._accept_observation(state.turns[-1], ToolResult(**data), timestamp)
            elif kind == "verification_result":
                state.turns[-1].verification = VerificationResult(**data)
                state.turns[-1].verification_at = timestamp
            elif kind == "plan_updated":
                state.plan = data["items"]
            elif kind == "context_compacted":
                state.summary = data["summary"]
                state.messages = data["messages"]
            elif kind == "snapshot_created":
                state.snapshots.append(data)
            elif kind == "recovery_guidance":
                state.messages.append({"role": "system", "content": data["content"]})
            elif kind == "failure_detected" and "signature" in data:
                state.last_failed_action = data["signature"]
                state.repeat_blocks = 0
            elif kind == "failure_detected" and data["category"] == "model_service":
                state.tokens = None
            elif kind == "recovery_action":
                if data["kind"] == "repeat_block":
                    state.repeat_blocks = data["count"]
                elif data["kind"] in ("alternative_action", "retry_succeeded"):
                    state.last_failed_action = None
                    state.repeat_blocks = 0
            elif kind == "workspace_restored":
                state.messages.append({
                    "role": "system",
                    "content": f"Workspace restored to snapshot {data['commit']}. Re-inspect files before editing.",
                })
            elif kind == "task_finished":
                state.stop_reason = data["stop_reason"]
        return state

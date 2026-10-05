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
    context_sources: list[dict[str, str]] = field(default_factory=list)
    memory_context: dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    snapshots: list[dict[str, Any]] = field(default_factory=list)
    pending_tools: dict[str, ToolCall] = field(default_factory=dict)
    last_failed_action: str | None = None
    repeat_blocks: int = 0
    project_check_commands: list[str] = field(default_factory=list)
    project_checks: list[dict[str, Any]] = field(default_factory=list)
    project_check_patch_sha256: str | None = None
    event_sink: Callable[[dict[str, Any]], None] | None = field(default=None, repr=False)

    @property
    def success(self) -> bool:
        return self.stop_reason in ("verified", "completed")

    @property
    def known_tokens(self) -> int:
        return sum(
            (turn.response.input_tokens or 0) + (turn.response.output_tokens or 0)
            for turn in self.turns
        ) + sum(
            (event["data"].get("input_tokens") or 0) + (event["data"].get("output_tokens") or 0)
            for event in self.events
            if event["event_type"] == "failure_detected" and event["data"]["category"] == "model_service"
        )

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
        self._clear_project_checks()

    def _clear_project_checks(self) -> None:
        self.project_checks = []
        self.project_check_patch_sha256 = None

    def set_project_check_suite(self, commands: list[str]) -> None:
        self.emit("project_check_suite", {"commands": commands})
        self.project_check_commands = commands
        self._clear_project_checks()

    def start_project_checks(self, patch_sha256: str) -> None:
        self.emit("project_check_started", {"patch_sha256": patch_sha256})
        self._clear_project_checks()

    def record_project_checks(self, checks: list[dict[str, Any]], patch_sha256: str) -> None:
        self.emit("project_check_completed", {"checks": checks, "patch_sha256": patch_sha256})
        self.project_checks = checks
        self.project_check_patch_sha256 = patch_sha256

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
                    "function": {"name": call.name, "arguments": json.dumps(call.arguments, ensure_ascii=False)},
                } for call in response.tool_calls],
            })
        else:
            self.messages.append({"role": "assistant", "content": response.final_message})
        if response.reasoning_content is not None:
            self.messages[-1]["reasoning_content"] = response.reasoning_content
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
        content = {"status": result.status}
        if result.output:
            content["output"] = result.output
        if result.error:
            content["error"] = result.error
        if result.exit_code is not None:
            content["exit_code"] = result.exit_code
        self.messages.append({
            "role": "tool",
            "tool_call_id": result.call_id,
            "content": json.dumps(content, ensure_ascii=False, separators=(",", ":")),
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

    def add_workflow_guidance(self, content: str) -> None:
        self.emit("workflow_guidance", {"content": content})
        self.messages.append({"role": "system", "content": content})

    def add_context_source(self, kind: str, path: str, content: str, digest: str) -> None:
        source = {"kind": kind, "path": path, "content": content, "sha256": digest}
        self.emit("context_source_added", source)
        self.context_sources.append(source)

    def set_memory_context(self, mode: str, query: str, entries: list[dict]) -> None:
        context = {"mode": mode, "query": query, "entries": entries}
        self.emit("memory_context_set", context)
        self.memory_context = context

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
        self._clear_project_checks()
        self.messages.append({
            "role": "system",
            "content": f"Workspace restored to snapshot {commit}. Re-inspect files before editing.",
        })

    def compact(self, max_chars: int, keep_messages: int, tool_output_chars: int = 4000) -> None:
        messages = []
        trimmed = 0
        for message in self.messages:
            if message["role"] == "tool":
                result = json.loads(message["content"])
                for field in ("output", "error"):
                    text = result.get(field)
                    if text and len(text) > tool_output_chars:
                        head = (tool_output_chars - 1) * 3 // 4
                        tail = tool_output_chars - 1 - head
                        result[field] = text[:head] + "…" + text[len(text) - tail:]
                        result["context_truncated_fields"] = [*result.get("context_truncated_fields", []), field]
                        trimmed += 1
                message = {**message, "content": json.dumps(result, ensure_ascii=False, separators=(",", ":"))}
            messages.append(message)
        start = 0
        if len(json.dumps(messages, ensure_ascii=False)) > max_chars:
            start = max(0, len(messages) - keep_messages)
        while start > 0 and messages[start]["role"] == "tool":
            start -= 1
        newest_turn = max((index for index, message in enumerate(messages)
                           if message["role"] == "assistant"), default=len(messages) - 1)
        while len(json.dumps(messages[start:], ensure_ascii=False)) > max_chars:
            following = start + 1
            while following < len(messages) and messages[following]["role"] == "tool":
                following += 1
            if following > newest_turn:
                break
            start = following
        if start == 0 and trimmed == 0:
            return
        messages = messages[start:]
        summary = self._history_summary(messages) if start else self.summary
        self.emit("context_compacted", {
            "summary": summary, "messages": messages,
            "discarded_messages": start, "trimmed_outputs": trimmed,
        })
        self.summary = summary
        self.messages = messages

    def _history_summary(self, retained: list[dict[str, Any]]) -> str:
        """Keep observed source, edits and command outcomes without summarizing reasoning."""
        retained_ids = {message["tool_call_id"] for message in retained if message["role"] == "tool"}
        task_step = next((event["step"] for event in reversed(self.events)
                          if event["event_type"] == "user_message"), 0)
        restored_step = max((event["step"] for event in self.events
                             if event["event_type"] == "workspace_restored"
                             or event["event_type"] == "recovery_action"
                             and event["data"]["kind"] == "snapshot_rollback"), default=-1)
        sources, changes, commands, failures = {}, {}, {}, {}
        edited_at = {}
        for step, turn in enumerate(self.turns[task_step:], task_step + 1):
            calls = {call.call_id: call for call in turn.response.tool_calls}
            for result, _ in turn.observations:
                call = calls[result.call_id]
                args = call.arguments
                passed = result.status == "completed" and result.exit_code in (None, 0)
                if passed and call.name in ("write_file", "edit_file"):
                    edited_at[args["path"]] = step
                if result.call_id in retained_ids or step <= restored_step:
                    continue
                if not passed:
                    failures[result.call_id] = f"{call.name}: {result.status}, exit={result.exit_code}; {(result.error or result.output)[:250]}"
                elif call.name in ("read_file", "read_file_range"):
                    path = args["path"]
                    location = f"{path}:{args['start_line']}-{args['end_line']}" if call.name == "read_file_range" else path
                    excerpt = result.output if len(result.output) <= 700 else result.output[:500] + "\n[excerpt omitted]\n" + result.output[-180:]
                    sources[location] = (path, step, f"Observed {location}:\n{excerpt}")
                elif call.name in ("write_file", "edit_file"):
                    path = args["path"]
                    replacement = args["new_text"] if call.name == "edit_file" else args["content"]
                    changes.pop(path, None)
                    changes[path] = f"Applied {call.name} to {path}; replacement excerpt:\n{replacement[:350]}"
                elif call.name == "run_shell":
                    command = args["command"]
                    commands.pop(command, None)
                    commands[command] = f"Ran {command[:200]}: exit={result.exit_code}\n{result.output[-300:]}"
        source_lines = [line for path, step, line in sorted(sources.values(), key=lambda entry: entry[1])
                        if step > edited_at.get(path, -1)][-3:]
        sections = [*list(changes.values())[-3:], *source_lines,
                    *list(commands.values())[-2:], *list(failures.values())[-2:]]
        lines = []
        for section in sections:
            if sum(len(line) + 1 for line in lines) + len(section) > 4000:
                break
            lines.append(section)
        return "\n".join(lines)

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
        pending_checks = []
        for event in events:
            data = event["data"]
            kind = event["event_type"]
            timestamp = event["timestamp"]
            state.events.append(event)
            if kind == "user_message":
                state.messages.append({"role": "user", "content": data["content"]})
                state.stop_reason = None
                state._clear_project_checks()
                pending_checks = []
            elif kind == "model_action":
                raw = data["response"]
                response = ModelResponse(
                    tool_calls=tuple(ToolCall(**call) for call in raw["tool_calls"]),
                    final_message=raw["final_message"],
                    input_tokens=raw["input_tokens"],
                    output_tokens=raw["output_tokens"],
                    reasoning_content=raw.get("reasoning_content"),
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
                if pending_checks:
                    state.project_checks = pending_checks
                    state.project_check_patch_sha256 = None
                    pending_checks = []
            elif kind == "project_check_suite":
                state.project_check_commands = data["commands"]
                state._clear_project_checks()
                pending_checks = []
            elif kind == "project_check_started":
                state._clear_project_checks()
                pending_checks = []
            elif kind == "project_check":
                pending_checks.append(data)
            elif kind == "project_check_completed":
                state.project_checks = data["checks"]
                state.project_check_patch_sha256 = data["patch_sha256"]
                pending_checks = []
            elif kind == "project_check_invalidated":
                state._clear_project_checks()
                pending_checks = []
            elif kind == "plan_updated":
                state.plan = data["items"]
            elif kind == "context_compacted":
                state.summary = data["summary"]
                state.messages = data["messages"]
            elif kind == "snapshot_created":
                state.snapshots.append(data)
            elif kind in ("recovery_guidance", "workflow_guidance"):
                state.messages.append({"role": "system", "content": data["content"]})
            elif kind == "context_source_added":
                state.context_sources.append(data)
            elif kind == "memory_context_set":
                state.memory_context = data
            elif kind == "failure_detected" and "signature" in data:
                state.last_failed_action = data["signature"]
                state.repeat_blocks = 0
            elif kind == "failure_detected" and data["category"] == "model_service":
                if data.get("input_tokens") is None or data.get("output_tokens") is None:
                    state.tokens = None
                elif state.tokens is not None:
                    state.tokens += data["input_tokens"] + data["output_tokens"]
            elif kind == "recovery_action":
                if data["kind"] == "repeat_block":
                    state.repeat_blocks = data["count"]
                elif data["kind"] in ("alternative_action", "retry_succeeded"):
                    state.last_failed_action = None
                    state.repeat_blocks = 0
            elif kind == "workspace_restored":
                state._clear_project_checks()
                pending_checks = []
                state.messages.append({
                    "role": "system",
                    "content": f"Workspace restored to snapshot {data['commit']}. Re-inspect files before editing.",
                })
            elif kind == "task_finished":
                state.stop_reason = data["stop_reason"]
        return state

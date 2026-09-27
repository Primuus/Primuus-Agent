"""Opt-in shell hooks run through the session's permission executor."""

from collections.abc import Callable
from dataclasses import asdict
from uuid import uuid4

from coding_agent.contracts import ToolCall, ToolResult
from coding_agent.session.state import SessionState


class HookExecutor:
    def __init__(
        self,
        hooks: dict[str, list[str]],
        execute_tool: Callable[[ToolCall], ToolResult],
        execute_shell: Callable[[ToolCall], ToolResult],
        state: SessionState,
    ) -> None:
        self.hooks = hooks
        self.execute_tool = execute_tool
        self.execute_shell = execute_shell
        self.state = state

    def _run_hooks(self, phase: str, call: ToolCall) -> ToolResult | None:
        for command in self.hooks.get(phase, []):
            hook = ToolCall(f"hook-{uuid4().hex}", "run_shell", {"command": command})
            self.state.emit("hook_started", {
                "phase": phase, "command": command, "tool_call_id": call.call_id,
            })
            result = self.execute_shell(hook)
            self.state.emit("hook_result", {
                "phase": phase, "command": command, "tool_call_id": call.call_id,
                "result": asdict(result),
            })
            if result.status != "completed" or result.exit_code != 0:
                return result
        return None

    def execute(self, call: ToolCall) -> ToolResult:
        before = self._run_hooks("before_tool", call)
        if before is not None:
            return ToolResult(
                call.call_id, call.name, "error", "",
                f"before_tool hook failed: {before.error or before.output}",
                before.exit_code, before.duration_ms,
            )
        result = self.execute_tool(call)
        after = self._run_hooks("after_tool", call)
        if after is not None and result.status == "completed" and result.exit_code in (None, 0):
            return ToolResult(
                call.call_id, call.name, "error", result.output,
                f"after_tool hook failed: {after.error or after.output}",
                after.exit_code, result.duration_ms + after.duration_ms,
            )
        return result

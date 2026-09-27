"""User controlled permission gate for repository actions."""

from collections.abc import Callable

from coding_agent.contracts import ToolCall, ToolResult


WRITE_TOOLS = {"write_file", "edit_file", "run_shell"}


class PermissionExecutor:
    def __init__(
        self,
        execute: Callable[[ToolCall], ToolResult],
        mode: str,
        ask: Callable[[str], str] = input,
        on_prompt: Callable[[ToolCall, bool], None] | None = None,
    ) -> None:
        self.execute_tool = execute
        self.mode = mode
        self.ask = ask
        self.on_prompt = on_prompt

    def execute(self, call: ToolCall) -> ToolResult:
        if call.name in WRITE_TOOLS:
            if self.mode == "read-only":
                return ToolResult(call.call_id, call.name, "error", "", "Action denied by read-only mode", None, 0)
            if self.mode == "ask":
                detail = call.arguments.get("command") or call.arguments.get("path", "")
                answer = self.ask(f"Allow {call.name} {str(detail)[:160]}? [y/N] ")
                allowed = answer.lower() in ("y", "yes")
                if self.on_prompt is not None:
                    self.on_prompt(call, allowed)
                if not allowed:
                    return ToolResult(call.call_id, call.name, "error", "", "Action declined", None, 0)
        return self.execute_tool(call)

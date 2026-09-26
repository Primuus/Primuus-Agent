"""Single-task agent loop, independent of model and execution backend."""

from collections.abc import Callable
from time import monotonic

from coding_agent.contracts import ToolCall, ToolResult
from coding_agent.harness.context import build_context
from coding_agent.harness.state import RunState
from coding_agent.harness.task import LoadedTask
from coding_agent.models.base import ModelBackend
from coding_agent.tools.specs import TOOL_SPECS


class Runner:
    def __init__(
        self,
        model: ModelBackend,
        execute: Callable[[ToolCall], ToolResult],
        verify: Callable[[], bool],
        max_steps: int,
        timeout_seconds: int,
    ) -> None:
        self.model = model
        self.execute = execute
        self.verify = verify
        self.max_steps = max_steps
        self.timeout_seconds = timeout_seconds

    def run(self, task: LoadedTask) -> RunState:
        state = RunState(task.spec.task_id)
        started = monotonic()
        for _ in range(self.max_steps):
            if monotonic() - started >= self.timeout_seconds:
                state.stop_reason = "timeout"
                return state
            try:
                response = self.model.generate(build_context(task, state), TOOL_SPECS)
            except (StopIteration, ValueError):
                state.stop_reason = "invalid_model_action"
                return state
            if response.tool_call is None:
                state.add_turn(response)
                state.stop_reason = "verified" if self.verify() else "final_unverified"
                return state
            result = self.execute(response.tool_call)
            state.add_turn(response, result)
            if self.verify():
                state.stop_reason = "verified"
                return state
        state.stop_reason = "max_steps"
        return state

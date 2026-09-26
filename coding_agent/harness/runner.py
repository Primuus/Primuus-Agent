"""Single-task agent loop, independent of model and execution backend."""

from collections.abc import Callable
from datetime import datetime, timezone
from time import monotonic

from coding_agent.contracts import ToolCall, ToolResult, VerificationResult
from coding_agent.harness.context import build_context
from coding_agent.harness.state import RunState
from coding_agent.harness.task import LoadedTask
from coding_agent.models.base import ModelBackend, ModelServiceError
from coding_agent.tools.specs import TOOL_SPECS
from coding_agent.verifier.base import VerifierError


class Runner:
    def __init__(
        self,
        model: ModelBackend,
        execute: Callable[[ToolCall], ToolResult],
        verify: Callable[[], VerificationResult],
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
                model_started = monotonic()
                response = self.model.generate(build_context(task, state), TOOL_SPECS)
            except (StopIteration, ValueError):
                state.stop_reason = "invalid_model_action"
                return state
            except ModelServiceError:
                state.stop_reason = "model_error"
                return state
            turn = state.add_turn(response, int((monotonic() - model_started) * 1000))
            if not response.tool_calls:
                try:
                    turn.verification = self.verify()
                    turn.verification_at = datetime.now(timezone.utc).isoformat()
                except VerifierError:
                    state.stop_reason = "verifier_error"
                    return state
                state.stop_reason = "verified" if turn.verification.passed else "final_unverified"
                return state
            for call in response.tool_calls:
                result = self.execute(call)
                turn.observations.append((result, datetime.now(timezone.utc).isoformat()))
            try:
                turn.verification = self.verify()
                turn.verification_at = datetime.now(timezone.utc).isoformat()
            except VerifierError:
                state.stop_reason = "verifier_error"
                return state
            if turn.verification.passed:
                state.stop_reason = "verified"
                return state
        state.stop_reason = "max_steps"
        return state

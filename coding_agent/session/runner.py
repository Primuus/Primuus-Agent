"""Model and tool loop used by both real repositories and task evaluation."""

from collections.abc import Callable
from time import monotonic

from coding_agent.contracts import ToolCall, ToolResult, VerificationResult
from coding_agent.models.base import ModelBackend, ModelServiceError
from coding_agent.session.context import build_context
from coding_agent.session.state import SessionSpec, SessionState
from coding_agent.tools.specs import TOOL_SPECS
from coding_agent.verifier.base import VerifierError


class SessionRunner:
    def __init__(
        self,
        model: ModelBackend,
        execute: Callable[[ToolCall], ToolResult],
        verify: Callable[[], VerificationResult] | None,
        max_steps: int,
        timeout_seconds: int,
        tool_specs: list[dict] = TOOL_SPECS,
    ) -> None:
        self.model = model
        self.execute = execute
        self.verify = verify
        self.max_steps = max_steps
        self.timeout_seconds = timeout_seconds
        self.tool_specs = tool_specs

    def run(self, spec: SessionSpec, state: SessionState | None = None) -> SessionState:
        state = state or SessionState(spec.session_id)
        state.add_user_message(spec.instructions)
        started = monotonic()
        for _ in range(max(0, self.max_steps - state.steps)):
            if monotonic() - started >= self.timeout_seconds:
                state.finish("timeout")
                return state
            try:
                model_started = monotonic()
                response = self.model.generate(build_context(state), self.tool_specs)
            except (StopIteration, ValueError):
                state.finish("invalid_model_action")
                return state
            except ModelServiceError:
                state.finish("model_error")
                return state
            turn = state.add_turn(response, int((monotonic() - model_started) * 1000))
            if not response.tool_calls:
                if self.verify is None:
                    state.finish("completed")
                    return state
                try:
                    state.add_verification(turn, self.verify())
                except VerifierError:
                    state.finish("verifier_error")
                    return state
                state.finish("verified" if turn.verification.passed else "final_unverified")
                return state
            for call in response.tool_calls:
                state.add_observation(turn, self.execute(call))
            if self.verify is not None:
                try:
                    state.add_verification(turn, self.verify())
                except VerifierError:
                    state.finish("verifier_error")
                    return state
                if turn.verification.passed:
                    state.finish("verified")
                    return state
        state.finish("max_steps")
        return state

"""Model and tool loop used by both real repositories and task evaluation."""

from collections.abc import Callable
import json
from math import ceil
from time import monotonic, sleep

from coding_agent.contracts import ToolCall, ToolResult, VerificationResult
from coding_agent.models.base import ModelBackend, ModelServiceError
from coding_agent.session.context import build_context
from coding_agent.session.recovery import (
    RecoveryPolicy, action_signature, alternative_guidance, failure_category,
)
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
        max_tokens: int | None = None,
        context_max_chars: int | None = None,
        context_keep_messages: int = 12,
        recovery: RecoveryPolicy = RecoveryPolicy(),
        checkpoint: Callable[[str], str] | None = None,
        rollback: Callable[[str], None] | None = None,
        verify_after_tools: bool = True,
        verification_success_reason: str = "verified",
        expose_verification_output: bool = False,
        post_tool_verify: Callable[[], VerificationResult | None] | None = None,
        budget_guidance: bool = False,
        context_tool_output_chars: int = 4000,
        max_output_tokens: int = 8192,
        initial_edit_budget_tokens: int | None = None,
    ) -> None:
        self.model = model
        self.execute = execute
        self.verify = verify
        self.max_steps = max_steps
        self.timeout_seconds = timeout_seconds
        self.tool_specs = tool_specs
        self.max_tokens = max_tokens
        self.context_max_chars = context_max_chars
        self.context_keep_messages = context_keep_messages
        self.recovery = recovery
        self.checkpoint = checkpoint
        self.rollback = rollback
        self.verify_after_tools = verify_after_tools
        self.verification_success_reason = verification_success_reason
        self.expose_verification_output = expose_verification_output
        self.post_tool_verify = post_tool_verify
        self.budget_guidance = budget_guidance
        self.context_tool_output_chars = context_tool_output_chars
        self.max_output_tokens = max_output_tokens
        self.initial_edit_budget_tokens = initial_edit_budget_tokens

    def _estimate_input(self, state: SessionState, messages: list[dict], tools: list[dict]) -> tuple[int, int]:
        size = len(json.dumps({"messages": messages, "tools": tools}, ensure_ascii=False).encode("utf-8"))
        estimate = ceil(size / 2)
        previous = next((event["data"] for event in reversed(state.events)
                         if event["event_type"] == "model_request" and event["step"] == state.steps), None)
        if previous is not None and state.turns[-1].response.input_tokens is not None:
            estimate = max(estimate, ceil(state.turns[-1].response.input_tokens * size / previous["input_bytes"]))
        return ceil(estimate * 1.2), size

    def _request_phase(self, state: SessionState) -> str:
        return next((event["data"]["phase"] for event in reversed(state.events)
                     if event["event_type"] == "model_request"), "work")

    def _prepare_request(self, state: SessionState) -> tuple[list[dict], list[dict], int, str]:
        tools = self.tool_specs
        output_limit = self.max_output_tokens
        phase = "work"
        task_start_step = next((event["step"] for event in reversed(state.events)
                                if event["event_type"] == "user_message"), 0)
        task_tokens = sum((turn.response.input_tokens or 0) + (turn.response.output_tokens or 0)
                          for turn in state.turns[task_start_step:])
        if (self.initial_edit_budget_tokens is not None
            and task_tokens >= self.initial_edit_budget_tokens
            and state.project_check_commands and state.project_check_patch_sha256 is None):
            phase = "edit"
            edit_steps = {event["step"] for event in state.events
                          if event["event_type"] == "model_request" and event["data"]["phase"] == "edit"}
            refreshed = any(
                step in edit_steps and any(call.name == "read_file_range" for call in turn.response.tool_calls)
                for step, turn in enumerate(state.turns[task_start_step:], task_start_step + 1)
            )
            edit_tools = {"write_file", "edit_file"}
            if not refreshed:
                edit_tools.add("read_file_range")
            tools = [tool for tool in tools if tool["name"] in edit_tools]
            if self._request_phase(state) != "edit":
                state.add_workflow_guidance(
                    "The initial investigation allowance is used. Broad discovery tools are closed. "
                    "One turn of focused read_file_range calls is available to recover source omitted "
                    "by compaction, followed by file editing tools. Prefer edit_file for the smallest "
                    "exact replacements. Configured checks run automatically and return failures. "
                    "If the evidence is insufficient, explain what is missing instead of claiming completion."
                )
        messages = build_context(state)
        estimate, size = self._estimate_input(state, messages, tools)
        ready = (bool(state.project_checks) and state.project_check_patch_sha256 is not None
                 and all(check["status"] == "completed" and check["exit_code"] == 0 for check in state.project_checks)
                 and all(item["status"] == "completed" for item in state.plan))
        remaining = self.max_tokens - state.known_tokens if self.max_tokens is not None else None
        reserve = estimate + self.max_output_tokens if self.budget_guidance else 0
        closing = self.budget_guidance and (
            self.max_steps - state.steps == 1
            or remaining is not None and remaining <= estimate + output_limit + reserve
        )
        if closing:
            state.compact(min(self.context_max_chars or 8000, 8000), 2, self.context_tool_output_chars)
            if ready:
                phase = "final"
                tools = []
                state.add_workflow_guidance(
                    "The current patch passed the project checks and the remaining budget is reserved "
                    "for your final answer. Review the original requirements and report the changes, "
                    "verification and any remaining limitations. Do not call more tools."
                )
            messages = build_context(state)
            if phase == "final":
                messages = [{key: value for key, value in message.items() if key != "reasoning_content"}
                            for message in messages]
            estimate, size = self._estimate_input(state, messages, tools)
            reserve = estimate + self.max_output_tokens if phase != "final" else 0
        if remaining is not None:
            output_limit = min(output_limit, remaining - estimate - reserve)
        state.emit("model_request", {
            "phase": phase, "input_bytes": size, "estimated_input_tokens": estimate,
            "max_output_tokens": output_limit, "reserved_tokens": reserve,
            "remaining_tokens": remaining,
        }, state.steps + 1)
        return messages, tools, output_limit, phase

    def run(self, spec: SessionSpec, state: SessionState | None = None) -> SessionState:
        state = state or SessionState(spec.session_id)
        if spec.instructions is not None:
            state.add_user_message(spec.instructions)
        else:
            state.emit("session_resumed", {})
            state.stop_reason = None
        started = monotonic()
        validation_retries = 0
        budget_warning_sent = False
        if (spec.instructions is None and self.verify is not None and state.turns
            and not state.turns[-1].response.tool_calls and self._request_phase(state) != "edit"):
            try:
                state.add_verification(state.turns[-1], self.verify())
            except VerifierError:
                state.record_failure("verification", {"reason": "verifier_error"})
                state.finish("verifier_error")
                return state
            if state.turns[-1].verification.passed:
                state.finish(self.verification_success_reason)
                return state
            state.record_failure("verification", {"reason": "check_failed"})
            if not self.recovery.enabled or self.recovery.validation_retries == 0:
                state.finish("final_unverified")
                return state
            validation_retries = 1
            state.emit("recovery_action", {"kind": "validation_retry", "attempt": 1})
            state.add_guidance("Final project check failed. Inspect the failure, fix the code, and rerun checks before finishing.")
        for _ in range(max(0, self.max_steps - state.steps)):
            if monotonic() - started >= self.timeout_seconds:
                state.finish("timeout")
                return state
            if self.max_tokens is not None and state.known_tokens >= self.max_tokens:
                state.finish("token_budget")
                return state
            if (self.budget_guidance and not budget_warning_sent
                and self.max_tokens is not None
                and state.known_tokens >= self.max_tokens / 3):
                state.add_workflow_guidance(
                    "One third of the token budget is used. If the relevant code and failure are "
                    "understood, make the focused edit now and use the configured checks. "
                    "Avoid more broad searches or unrelated edge cases; leave budget for the final answer."
                )
                budget_warning_sent = True
            if self.context_max_chars is not None:
                state.compact(self.context_max_chars, self.context_keep_messages, self.context_tool_output_chars)
            messages, tools, output_limit, phase = self._prepare_request(state)
            if output_limit <= 0:
                state.finish("token_budget")
                return state
            model_attempt = 0
            while True:
                try:
                    model_started = monotonic()
                    response = self.model.generate(messages, tools, max_output_tokens=output_limit)
                    break
                except (StopIteration, ValueError):
                    state.finish("invalid_model_action")
                    return state
                except ModelServiceError as error:
                    if error.input_tokens is None or error.output_tokens is None:
                        state.tokens = None
                    elif state.tokens is not None:
                        state.tokens += error.input_tokens + error.output_tokens
                    state.record_failure("model_service", {
                        "retryable": error.retryable, "message": str(error),
                        "attempt": model_attempt + 1,
                        "input_tokens": error.input_tokens, "output_tokens": error.output_tokens,
                    })
                    if (not self.recovery.enabled or not error.retryable
                        or model_attempt >= self.recovery.model_retries
                        or monotonic() - started >= self.timeout_seconds):
                        state.finish("model_error")
                        return state
                    model_attempt += 1
                    messages, tools, output_limit, phase = self._prepare_request(state)
                    if output_limit <= 0:
                        state.finish("token_budget")
                        return state
                    state.emit("recovery_action", {"kind": "model_retry", "attempt": model_attempt})
                    sleep(min(0.5 * 2 ** (model_attempt - 1),
                              max(0, self.timeout_seconds - (monotonic() - started))))
            turn = state.add_turn(response, int((monotonic() - model_started) * 1000))
            if not response.tool_calls:
                if phase == "edit":
                    state.record_failure("verification", {"reason": "initial_edit_missing"})
                    state.finish("final_unverified")
                    return state
                if self.verify is None:
                    state.finish("completed")
                    return state
                try:
                    state.add_verification(turn, self.verify())
                except VerifierError:
                    state.record_failure("verification", {"reason": "verifier_error"})
                    state.finish("verifier_error")
                    return state
                if turn.verification.passed:
                    state.finish(self.verification_success_reason)
                    return state
                state.record_failure("verification", {"reason": "check_failed"})
                if not self.recovery.enabled or validation_retries >= self.recovery.validation_retries:
                    state.finish("final_unverified")
                    return state
                validation_retries += 1
                state.emit("recovery_action", {"kind": "validation_retry", "attempt": validation_retries})
                detail = ""
                if self.expose_verification_output:
                    detail = f" Output: {(turn.verification.output + ' ' + (turn.verification.error or ''))[:4000]}"
                state.add_guidance("Final project check failed. Inspect the failure, fix the code, and rerun checks before finishing." + detail)
                continue
            guidance = []
            for call in response.tool_calls:
                signature = action_signature(call)
                repeated = self.recovery.enabled and signature == state.last_failed_action
                if self.recovery.enabled and not repeated:
                    state.clear_failed_action()
                state.start_tool(call)
                checkpoint = None
                if repeated:
                    state.record_repeat_block(signature, call.name)
                    result = ToolResult(
                        call.call_id, call.name, "error", "",
                        "Repeated failed action blocked; inspect the failure and choose another action",
                        None, 0,
                    )
                    category = "tool"
                else:
                    if (self.recovery.enabled and self.checkpoint is not None
                        and call.name in ("write_file", "edit_file", "run_shell")):
                        checkpoint = self.checkpoint(f"before {call.name} at step {state.steps}")
                    result = self.execute(call)
                    if (self.recovery.enabled and result.status == "timeout"
                        and call.name in ("read_file", "read_file_range", "list_files", "search_text", "git_status", "git_diff")):
                        for attempt in range(1, self.recovery.tool_retries + 1):
                            state.record_failure("tool", {
                                "signature": signature, "tool": call.name,
                                "status": result.status, "attempt": attempt,
                            })
                            state.emit("recovery_action", {
                                "kind": "tool_retry", "tool": call.name, "attempt": attempt,
                            })
                            result = self.execute(call)
                            if result.status != "timeout":
                                break
                        if failure_category(call, result) is None:
                            state.clear_failed_action("retry_succeeded")
                    category = failure_category(call, result)
                if category is not None:
                    if not repeated:
                        state.record_failure(category, {
                            "signature": signature, "tool": call.name,
                            "status": result.status, "exit_code": result.exit_code,
                        })
                    if (self.recovery.enabled and checkpoint is not None
                        and self.rollback is not None and category in ("tool", "build", "test")):
                        self.rollback(checkpoint)
                        state.emit("recovery_action", {
                            "kind": "snapshot_rollback", "commit": checkpoint,
                            "tool": call.name,
                        })
                        guidance.append("The workspace was restored to the checkpoint before this failed action.")
                state.add_observation(turn, result)
                if category is not None and self.recovery.enabled:
                    guidance.append(alternative_guidance(category, call))
            for instruction in guidance:
                state.add_guidance(instruction)
            if self.recovery.enabled and state.repeat_blocks >= self.recovery.repeat_blocks:
                state.finish("recovery_exhausted")
                return state
            if self.post_tool_verify is not None:
                try:
                    progress = self.post_tool_verify()
                except VerifierError:
                    state.record_failure("verification", {"reason": "verifier_error"})
                    state.finish("verifier_error")
                    return state
                if progress is not None:
                    state.add_verification(turn, progress)
                    if progress.passed:
                        state.add_workflow_guidance(
                            "The configured project checks passed for the current patch. "
                            "Review the user's requirements; if they are satisfied, give a final reply now."
                        )
                    else:
                        detail = (progress.output + " " + (progress.error or ""))[:4000]
                        state.add_workflow_guidance(
                            "The configured project checks failed for the current patch. "
                            "Fix the reported problem before finishing. Output: " + detail
                        )
            if self.verify is not None and self.verify_after_tools:
                try:
                    state.add_verification(turn, self.verify())
                except VerifierError:
                    state.record_failure("verification", {"reason": "verifier_error"})
                    state.finish("verifier_error")
                    return state
                if turn.verification.passed:
                    state.finish("verified")
                    return state
        state.finish("max_steps")
        return state

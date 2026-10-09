"""Model and tool loop used by both real repositories and task evaluation."""

from collections.abc import Callable
import json
from math import ceil
from time import monotonic, sleep

from coding_agent.contracts import ToolCall, ToolResult, VerificationResult
from coding_agent.models.base import ModelBackend, ModelServiceError
from coding_agent.session.context import build_context, build_final_context, build_planning_context, build_progress_context
from coding_agent.session.planning import PLAN_PHASES, apply_progress, parse_initial_plan
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
        action_review_after_tokens: int = 40000,
        action_review_after_steps: int = 6,
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
        self.action_review_after_tokens = action_review_after_tokens
        self.action_review_after_steps = action_review_after_steps

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
                     if event["event_type"] == "model_request" and event["step"] == state.steps), "work")

    def _remind_repeated_reads(self, state: SessionState) -> None:
        recent = []
        for turn in state.turns[-6:]:
            calls = {call.call_id: call for call in turn.response.tool_calls}
            recent.extend((calls[result.call_id], result) for result, _ in turn.observations)
        if len(recent) < 3:
            return
        call, result = recent[-1]
        if call.name not in {"read_file", "read_file_range", "search_text", "list_files", "git_status", "git_diff"}:
            return
        signature = (action_signature(call), result.status, result.output, result.error)
        same = [(action_signature(item), value.status, value.output, value.error) == signature
                for item, value in recent[-4:]]
        repeated = all(same[-3:]) and not (len(same) == 4 and same[0])
        source_ref = None
        if call.name in ("read_file", "read_file_range") and result.status == "completed":
            def lines(item: ToolCall, value: ToolResult) -> dict[int, str]:
                if item.name == "read_file":
                    return dict(enumerate(value.output.splitlines(), 1))
                return {int(number): text for line in value.output.splitlines()
                        for number, text in [line.split(": ", 1)]}

            current_lines = lines(call, result)
            current_ids = {item.call_id for item in state.turns[-1].response.tool_calls}
            saved_ids = {source["call_id"] for source in state.continuation.get("source_snapshots", [])}
            for previous, observation in reversed(recent[:-1]):
                if previous.name in ("write_file", "edit_file", "run_shell"):
                    break
                if (previous.name not in ("read_file", "read_file_range")
                    or previous.call_id in current_ids
                    or observation.status != "completed"
                    or previous.arguments["path"].removeprefix("/workspace/")
                    != call.arguments["path"].removeprefix("/workspace/")):
                    continue
                if (previous.name == "read_file" and len(observation.output) > self.context_tool_output_chars
                    and previous.call_id not in saved_ids):
                    continue
                prior_lines = lines(previous, observation)
                if current_lines and all(prior_lines.get(number) == text for number, text in current_lines.items()):
                    source_ref = previous.call_id
                    break
        if not repeated and source_ref is None:
            return
        digest = state.workspace_patch.get("sha256")
        if source_ref is not None and any(
            event["event_type"] == "investigation_stalled"
            and event["data"].get("patch_sha256") == digest
            and event["data"]["arguments"].get("path", "").removeprefix("/workspace/")
            == call.arguments["path"].removeprefix("/workspace/")
            for event in state.events
        ):
            return
        state.emit("investigation_stalled", {
            "tool": call.name, "arguments": call.arguments,
            "source_ref": source_ref, "patch_sha256": digest,
        })
        state.add_workflow_guidance(
            "Recent reads returned source lines already observed, without a new edit or shell action. "
            "Use the current working notes and saved source evidence. State what remains unknown "
            "and choose a new next action: a different targeted query, a minimal reproduction, or "
            "an edit supported by the observed code. For a multi-part task, update the active "
            "requirement's hypothesis and next action before moving to another file."
        )

    def _prepare_request(self, state: SessionState) -> tuple[list[dict], list[dict], int, str]:
        tools = self.tool_specs
        output_limit = self.max_output_tokens
        phase = "work"
        messages = build_context(state)
        if self.budget_guidance and not state.plan and any(tool["name"] == "update_plan" for tool in tools):
            messages, tools, phase = build_planning_context(state), [], "plan"
            output_limit = min(output_limit, 1536)
        elif self.budget_guidance and self._progress_due(state):
            messages, tools, phase = build_progress_context(state), [], "plan_progress"
            output_limit = min(output_limit, 1536)
        elif self.budget_guidance and self._action_due(state):
            messages, tools, phase = build_progress_context(state, before_edit=True), [], "plan_action"
            output_limit = min(output_limit, 1536)
        estimate, size = self._estimate_input(state, messages, tools)
        ready = (bool(state.project_checks) and state.project_check_patch_sha256 is not None
                 and all(check["status"] == "completed" and check["exit_code"] == 0 for check in state.project_checks)
                 and state.plan_complete)
        remaining = self.max_tokens - state.known_tokens if self.max_tokens is not None else None
        final_messages = build_final_context(state) if self.budget_guidance else []
        final_limit = min(self.max_output_tokens, 1024)
        final_estimate = self._estimate_input(state, final_messages, [])[0] if self.budget_guidance else 0
        reserve = final_estimate + final_limit if self.budget_guidance else 0
        if remaining is not None:
            output_limit = min(output_limit, remaining - estimate - reserve)
        closing = self.budget_guidance and (
            self.max_steps - state.steps == 1
            or remaining is not None and output_limit < final_limit
        )
        if closing:
            phase = "final" if ready else (
                "step_report" if self.max_steps - state.steps == 1 else "budget_report"
            )
            messages, tools = final_messages, []
            messages[0]["content"] += " The work allowance is ending; report any remaining work explicitly."
            output_limit = final_limit
            estimate, size = self._estimate_input(state, messages, tools)
            reserve = 0
        if remaining is not None:
            output_limit = min(output_limit, remaining - estimate - reserve)
        state.emit("model_request", {
            "phase": phase, "input_bytes": size, "estimated_input_tokens": estimate,
            "max_output_tokens": output_limit, "reserved_tokens": reserve,
            "remaining_tokens": remaining,
        }, state.steps + 1)
        return messages, tools, output_limit, phase

    def _progress_due(self, state: SessionState) -> bool:
        if (not any(item["status"] == "in_progress" for item in state.plan)
            or not state.project_checks or state.project_check_patch_sha256 is None
            or state.project_check_patch_sha256 != state.workspace_patch.get("sha256")
            or any(check["status"] != "completed" or check["exit_code"] != 0
                   for check in state.project_checks)):
            return False
        checked = next((event for event in reversed(state.events)
                        if event["event_type"] == "project_check_completed"), None)
        updated = max((event["step"] for event in state.events
                       if event["event_type"] == "plan_updated"), default=-1)
        return checked is not None and checked["step"] > updated

    def _action_due(self, state: SessionState) -> bool:
        if not any(item["status"] == "in_progress" for item in state.plan):
            return False
        source_step = max(state.requirement_started_step, max(
            (event["step"] for event in state.events
             if event["event_type"] in ("workspace_patch", "workspace_restored")), default=0,
        ))
        action_steps = {event["step"] for event in state.events
                        if event["event_type"] == "model_request" and event["data"]["phase"] == "plan_action"}
        reviewed_step = max((event["step"] for event in state.events
                             if event["event_type"] == "plan_updated" and event["step"] in action_steps), default=0)
        boundary = max(source_step, reviewed_step)
        turns = state.turns[boundary:]
        work_steps = sum(bool(turn.response.tool_calls) for turn in turns)
        tokens = sum((turn.response.input_tokens or 0) + (turn.response.output_tokens or 0) for turn in turns)
        repeated = any(event["event_type"] == "investigation_stalled" and event["step"] > boundary
                       for event in state.events)
        if (work_steps < self.action_review_after_steps and tokens < self.action_review_after_tokens
            and not repeated):
            return False
        active = next(item for item in state.plan if item["status"] == "in_progress")
        paths = {path.removeprefix("/workspace/") for path in active.get("files", [])}
        for turn in state.turns[source_step:]:
            calls = {call.call_id: call for call in turn.response.tool_calls}
            if any(result.status == "completed"
                   and calls[result.call_id].name in ("read_file", "read_file_range")
                   and (not paths or calls[result.call_id].arguments["path"].removeprefix("/workspace/") in paths)
                   for result, _ in turn.observations):
                return True
        return False

    def _accept_plan(self, state: SessionState, phase: str = "plan") -> bool:
        try:
            content = state.turns[-1].response.final_message
            if content is None:
                raise ValueError("Planning requires a JSON response without tool calls")
            items = parse_initial_plan(content) if phase == "plan" else apply_progress(state.plan, content)
            if phase == "plan_action" and any(item["status"] != previous["status"]
                                              for item, previous in zip(items, state.plan)):
                raise ValueError("An action review without edits must keep the current requirement in_progress")
        except ValueError as error:
            state.record_failure("planning", {"message": str(error)})
            state.finish("invalid_model_action")
            return False
        completed_before = sum(item["status"] == "completed" for item in state.plan)
        state.update_plan(items)
        if self.checkpoint is not None and sum(item["status"] == "completed" for item in items) > completed_before:
            self.checkpoint("plan progress")
        return True

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
        if (spec.instructions is None and state.turns and self._request_phase(state) == "plan"
            and not state.plan and not self._accept_plan(state)):
            return state
        if (spec.instructions is None and state.turns and self._request_phase(state) in ("plan_progress", "plan_action")
            and not any(event["event_type"] == "plan_updated" and event["step"] == state.steps
                        for event in state.events)
            and not self._accept_plan(state, self._request_phase(state))):
            return state
        if (spec.instructions is None and self.verify is not None and state.turns
            and not state.turns[-1].response.tool_calls
            and self._request_phase(state) not in (*PLAN_PHASES, "edit", "budget_report", "step_report")):
            if not state.plan_complete:
                state.finish("final_unverified")
                return state
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
                self._remind_repeated_reads(state)
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
            turn = state.add_turn(response, int((monotonic() - model_started) * 1000),
                                  include_in_conversation=phase not in PLAN_PHASES)
            if phase in PLAN_PHASES:
                if not self._accept_plan(state, phase):
                    return state
                continue
            if not response.tool_calls:
                if phase in ("budget_report", "step_report"):
                    state.finish("token_budget" if phase == "budget_report" else "max_steps")
                    return state
                if not state.plan_complete:
                    state.record_failure("verification", {"reason": "unfinished_plan"})
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
            offered_tools = {tool["name"] for tool in tools}
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
                elif call.name not in offered_tools:
                    result = ToolResult(
                        call.call_id, call.name, "error", "",
                        f"Tool unavailable in {phase} phase; available tools: {', '.join(sorted(offered_tools)) or 'none'}",
                        None, 0,
                    )
                    category = "tool"
                else:
                    if (self.recovery.enabled and self.checkpoint is not None
                        and call.name in ("write_file", "edit_file", "run_shell", "run_checks")):
                        checkpoint = self.checkpoint(f"before {call.name} at step {state.steps}")
                    result = (state.read_tool_output(call) if call.name == "read_tool_output"
                              else self.execute(call))
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
                            "Passing existing checks alone does not prove every requested fix. "
                            "Review each requirement against your actual edits; continue relevant work "
                            "if needed, otherwise give a final reply."
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

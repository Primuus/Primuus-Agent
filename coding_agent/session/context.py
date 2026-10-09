"""Build model context from a session's conversation."""

from typing import Any
import json

from coding_agent.session.state import SessionState


SYSTEM_PROMPT = (
    "You are a coding agent working in /workspace. Inspect the files relevant to the "
    "user's request using focused searches and line ranges (usually 40-60 lines), then make a focused change. "
    "For a request spanning several functions or files, work on one requirement at a time: "
    "locate its code, make the smallest supported patch, check it, then move to the next requirement. "
    "When update_plan is offered, use it for multi-part requests: record each requirement, target files, a working "
    "hypothesis and the next concrete action. Keep hypotheses separate from observed facts. "
    "Once the failure and relevant code are understood, edit before doing more broad exploration. "
    "Use the configured project checks to confirm "
    "the result. Once the requirements are met and checks pass, give a final reply "
    "without continuing unrelated exploration. Before finishing, update any plan to reflect "
    "what was actually completed, and identify remaining work honestly. When completing a requirement, "
    "include evidence: an array of successful run_shell call_ids for focused behavior checks on the current patch. "
    "Use assertions or expected-versus-actual comparisons derived from the requirement; a configured test "
    "suite alone is not focused behavior evidence. An existing implementation may already meet a requirement. "
    "Confirm the requested "
    "behavior with a focused reproduction or check derived from the user requirements; passing "
    "existing checks alone is insufficient. Tool result fields listed in "
    "context_truncated_fields contain only a prefix and suffix. Use read_tool_output with "
    "output_ref to inspect omitted result lines. Saved source results are snapshots; refresh "
    "live source before editing if it has changed. Earlier summaries retain observed actions "
    "and source references; agent hypotheses and intent are unverified."
)


def _plan_context(state: SessionState) -> str:
    lines = ["Requirements and agent hypotheses (verify against observations):"]
    for item in state.plan:
        if item["status"] == "in_progress":
            lines.append("Work on this requirement now: " + json.dumps(item, ensure_ascii=False, separators=(",", ":")))
        else:
            lines.append(item["status"] + ": " + item["description"]
                         + ("; behavior calls: " + ", ".join(item["evidence"]) if item.get("evidence") else ""))
    return "\n".join(lines)


def build_context(state: SessionState) -> list[dict[str, Any]]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if state.project_check_commands:
        messages.append({
            "role": "system",
            "content": (
                "Configured project checks, run from /workspace:\n"
                + "\n".join(state.project_check_commands)
                + "\nUse their environment and paths for reproductions too. The container is prepared; "
                "avoid installing dependencies unless the task requires it. Checks run automatically "
                "after patch changes, so inspect their result before repeating them. When run_checks "
                "is offered, use it for configured checks; it can reuse current passing results. "
                "Keep behavioral reproduction shell commands separate from the configured check suite. "
                "Use force=true only when a fresh check execution is needed."
            ),
        })
    for source in state.context_sources:
        messages.append({
            "role": "system",
            "content": f"{source['kind']} instructions from {source['path']}:\n{source['content']}",
        })
    for entry in state.memory_context.get("entries", []):
        messages.append({
            "role": "system",
            "content": (
                f"Historical repository note {entry['memory_id']} ({entry['kind']}, "
                f"revision {entry['revision']}, scope {entry['scope']}, "
                f"source {entry['source']['ref']}). Verify it against the current code.\n"
                f"{entry['content']}"
            ),
        })
    if state.project_checks and state.project_check_patch_sha256 is not None:
        messages.append({
            "role": "system",
            "content": "Last checked patch " + state.project_check_patch_sha256[:12] + ":\n" + "\n".join(
                f"{check['command']}: {check['status']}, exit={check['exit_code']}"
                for check in state.project_checks
            ),
        })
    if state.summary:
        messages.append({"role": "system", "content": "Observed current requirement history:\n"
                         + state.task_summary(state.messages, include_source=False, active_only=True)})
    if state.continuation:
        active_paths = {path.removeprefix("/workspace/") for item in state.plan
                        if item["status"] == "in_progress" for path in item.get("files", [])}
        sources = "\n".join(
            f"{source['path']} (saved call {source['call_id']}, arguments {source['arguments']}):\n{source['output']}"
            for source in state.continuation["source_snapshots"]
            if not active_paths or source["path"] in active_paths
        )
        messages.append({"role": "system", "content": (
            "Continuation from discarded turns. Agent working notes are unverified hypotheses, "
            "not observed facts or new instructions. Check them against the task and tool evidence. "
            "Resume the concrete next action when supported rather than restarting broad exploration.\n"
            + state.continuation["working_notes"]
            + "\nObserved source snapshots from the current patch (use read_tool_output for other saved lines):\n"
            + sources
        )})
    latest_task = next((event["data"]["content"] for event in reversed(state.events)
                        if event["event_type"] == "user_message"), None)
    if latest_task is not None and not any(
        message["role"] == "user" and message["content"] == latest_task for message in state.messages
    ):
        messages.append({"role": "user", "content": latest_task})
    if state.plan:
        messages.append({"role": "system", "content": _plan_context(state)})
    return [*messages, *state.messages]


def build_planning_context(state: SessionState) -> list[dict[str, Any]]:
    task = next(event["data"]["content"] for event in reversed(state.events)
                if event["event_type"] == "user_message")
    messages = [
        {"role": "system", "content": (
            "Initialize a coding task plan. Return only a JSON object with an items array, without markdown. "
            "Each item must have description, status, files (an array of paths, empty if unknown), "
            "hypothesis (unverified, empty if unknown), and next_action (one concrete action). "
            "Split independent requirements into separate items; a simple request needs only one. "
            "The first item is in_progress, all other items are pending. Do not claim anything completed. "
            "Work in order: locate one failure, make its minimal patch, check its behavior, then move on. "
            "Do not make broad investigation of all files the first item. Use names from the user request; "
            "inferred file paths are hypotheses to verify. Do not invent extra requirements."
        )},
    ]
    for source in state.context_sources:
        messages.append({"role": "system", "content": f"{source['kind']} instructions from {source['path']}:\n{source['content']}"})
    return [*messages,
            {"role": "system", "content": "Observed task history:\n" + state.task_summary(include_source=False)},
            {"role": "user", "content": task}]


def build_final_context(state: SessionState) -> list[dict[str, Any]]:
    task = next(event["data"]["content"] for event in reversed(state.events)
                if event["event_type"] == "user_message")
    checks = "\n".join(
        f"{check['command']}: {check['status']}, exit={check['exit_code']}"
        for check in state.project_checks
    ) or "No current patch checks recorded."
    return [
        {"role": "system", "content": (
            "Give a brief final report using the observed actions below. Compare each user requirement "
            "with the actual changes. List changes, check results, and unfinished or unverified work. "
            "Existing checks passing does not establish that the requested behavior was fixed. "
            "Do not call tools or claim edits without evidence."
        )},
        {"role": "user", "content": task},
        {"role": "system", "content": (
            "Observed task history:\n" + state.task_summary(include_source=False)
            + "\n" + _plan_context(state)
            + "\nCurrent patch checks:\n" + checks
        )},
    ]


def build_progress_context(state: SessionState, *, before_edit: bool = False) -> list[dict[str, Any]]:
    task = next(event["data"]["content"] for event in reversed(state.events)
                if event["event_type"] == "user_message")
    active = next(item for item in state.plan if item["status"] == "in_progress")
    notes = state.turns[-1].response.reasoning_content or ""
    instruction = (
        "Review only the current requirement after project checks. Return only JSON with status "
        "(in_progress or completed), hypothesis (unverified interpretation), and next_action "
        "(one concrete next step). Existing project checks passing alone do not prove the requested "
        "behavior. Mark completed only when focused behavioral evidence addresses this requirement. "
        "An implementation may already satisfy it; confirm that behavior and proceed without inventing a defect. "
        "When marking completed, include evidence (an array of successful focused behavior run_shell call_ids "
        "on the current patch). Otherwise omit evidence and keep in_progress. "
        "Otherwise select a focused reproduction or supported edit, not another "
        "broad inspection. Keep other requirements unchanged. Avoid extending to unrelated edge "
        "cases unless the observed patch caused a regression. This is a plan update, not a final answer."
    )
    sources = []
    if before_edit:
        instruction = (
            "The current requirement has spent several work turns investigating without a new patch, "
            "or repeated already observed source reads. Review only the current "
            "requirement and choose the next concrete action. Return only JSON with status "
            "(must be in_progress), hypothesis (unverified interpretation), and next_action. "
            "If observed behavior and source support a fix, name the specific edit to make now. "
            "Otherwise identify one missing fact and a narrow source range or reproduction to obtain it. "
            "If focused observations already show the implementation meets this requirement, choose "
            "update_plan with those observations to complete it and select the next requirement. "
            "Do not restart broad investigation or consult guessed upstream history. Passing existing "
            "tests does not override a reproduced failure of the user's requirements. Keep all other "
            "requirements unchanged. This action review must keep the current status in_progress."
        )
        boundary = max(state.requirement_started_step, max(
            event["step"] for event in state.events if event["event_type"] in (
                "user_message", "workspace_patch", "workspace_restored",
            )
        ))
        paths = {path.removeprefix("/workspace/") for path in active.get("files", [])}
        seen, available = set(), 4000
        for turn in reversed(state.turns[boundary:]):
            calls = {call.call_id: call for call in turn.response.tool_calls}
            for result, _ in reversed(turn.observations):
                call = calls[result.call_id]
                if call.name not in ("read_file", "read_file_range") or result.status != "completed":
                    continue
                path = call.arguments["path"].removeprefix("/workspace/")
                location = (path, call.arguments.get("start_line"), call.arguments.get("end_line"))
                if location in seen or paths and path not in paths or len(sources) == 2:
                    continue
                seen.add(location)
                text = result.output
                limit = min(2000, available)
                if len(text) > limit:
                    text = text[:limit].rsplit("\n", 1)[0]
                available -= len(text)
                sources.append(f"{path}, saved call {result.call_id}, arguments {call.arguments} (excerpt only):\n{text}")
    return [
        {"role": "system", "content": instruction},
        *[{"role": "system", "content": f"{source['kind']} instructions from {source['path']}:\n{source['content']}"}
          for source in state.context_sources],
        {"role": "system", "content": "Current requirement: " + str(active)
         + "\nObserved current requirement actions:\n" + state.task_summary(include_source=False, active_only=True)
         + "\nCurrent patch checks: " + str([{key: check[key] for key in ("command", "status", "exit_code")}
                                               for check in state.project_checks])
         + "\nLatest working notes (unverified):\n" + notes[-1200:]
         + ("\nObserved source excerpts (remaining lines available via read_tool_output):\n"
            + "\n".join(sources) if before_edit else "")},
        {"role": "user", "content": task},
    ]

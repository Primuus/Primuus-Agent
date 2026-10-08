"""Build model context from a session's conversation."""

from typing import Any

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
    "what was actually completed, and identify remaining work honestly. Confirm the requested "
    "behavior with a focused reproduction or check derived from the user requirements; passing "
    "existing checks alone is insufficient. Tool result fields listed in "
    "context_truncated_fields contain only a prefix and suffix. Use read_tool_output with "
    "output_ref to inspect omitted result lines. Saved source results are snapshots; refresh "
    "live source before editing if it has changed. Earlier summaries retain observed actions "
    "and source references; agent hypotheses and intent are unverified."
)


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
    if state.plan:
        messages.append({"role": "system", "content": "Agent plan and hypotheses (verify against observations): " + str(state.plan)})
    if state.project_checks and state.project_check_patch_sha256 is not None:
        messages.append({
            "role": "system",
            "content": "Last checked patch " + state.project_check_patch_sha256[:12] + ":\n" + "\n".join(
                f"{check['command']}: {check['status']}, exit={check['exit_code']}"
                for check in state.project_checks
            ),
        })
    if state.summary:
        messages.append({"role": "system", "content": "Earlier session summary: " + state.summary})
    if state.continuation:
        sources = "\n".join(
            f"{source['path']} (saved call {source['call_id']}, arguments {source['arguments']}):\n{source['output']}"
            for source in state.continuation["source_snapshots"]
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
    messages.extend(state.messages)
    if state.plan:
        active = next((item for item in state.plan if item["status"] == "in_progress"), None)
        if active is not None:
            messages.append({"role": "system", "content": (
                "Work on this requirement now: " + active["description"]
                + "\nTarget files (verify their paths): " + str(active.get("files", []))
                + "\nWorking hypothesis (unverified): " + active.get("hypothesis", "")
                + "\nNext action: " + active.get("next_action", "Locate the code, make a supported edit, then check it.")
                + "\nUse focused source ranges. Once its failure and implementation are understood, "
                "make the minimal patch before investigating a different independent requirement. "
                "After its behavior is checked, update_plan to complete it and select the next requirement."
            )})
    return messages


def build_planning_context(state: SessionState) -> list[dict[str, Any]]:
    task = next(event["data"]["content"] for event in reversed(state.events)
                if event["event_type"] == "user_message")
    return [
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
        {"role": "user", "content": task},
        {"role": "system", "content": "Observed task history:\n" + state.task_summary(include_source=False)},
    ]


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
            + "\nCurrent plan: " + str(state.plan)
            + "\nCurrent patch checks:\n" + checks
        )},
    ]

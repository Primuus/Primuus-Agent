"""Build model context from a session's conversation."""

from typing import Any

from coding_agent.session.state import SessionState


SYSTEM_PROMPT = (
    "You are a coding agent working in /workspace. Inspect the files relevant to the "
    "user's request using focused searches and line ranges (usually 40-60 lines), then make a focused change. "
    "For a request spanning several functions or files, identify each target before editing. "
    "When update_plan is offered, use it for multi-part requests: record each requirement, target files, a working "
    "hypothesis and the next concrete action. Keep hypotheses separate from observed facts. "
    "Once the failure and relevant code are understood, edit before doing more broad exploration. "
    "Use the configured project checks to confirm "
    "the result. Once the requirements are met and checks pass, give a final reply "
    "without continuing unrelated exploration. Tool result fields listed in "
    "context_truncated_fields contain only a prefix and suffix; use line ranges or "
    "focused queries for the omitted content. Earlier summaries contain observed excerpts, "
    "not complete files or inferred conclusions; refresh a relevant range if exact source is missing."
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
                "after patch changes, so inspect their result before repeating them."
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
    latest_task = next((event["data"]["content"] for event in reversed(state.events)
                        if event["event_type"] == "user_message"), None)
    if latest_task is not None and not any(
        message["role"] == "user" and message["content"] == latest_task for message in state.messages
    ):
        messages.append({"role": "user", "content": latest_task})
    return [*messages, *state.messages]


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
            "Observed task history:\n" + state._history_summary([])
            + "\nCurrent plan: " + str(state.plan)
            + "\nCurrent patch checks:\n" + checks
        )},
    ]

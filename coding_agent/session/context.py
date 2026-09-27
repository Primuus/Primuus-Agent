"""Build model context from a session's conversation."""

from typing import Any

from coding_agent.session.state import SessionState


SYSTEM_PROMPT = (
    "You are a coding agent working in /workspace. Use the available tools to "
    "inspect and modify the repository. Give a final reply when you are done."
)


def build_context(state: SessionState) -> list[dict[str, Any]]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
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
        messages.append({"role": "system", "content": "Current plan: " + str(state.plan)})
    if state.summary:
        messages.append({"role": "system", "content": "Earlier session summary: " + state.summary})
    return [*messages, *state.messages]

"""Build model context from a session's conversation."""

from typing import Any

from coding_agent.session.state import SessionState


SYSTEM_PROMPT = (
    "You are a coding agent working in /workspace. Use the available tools to "
    "inspect and modify the repository. Give a final reply when you are done."
)


def build_context(state: SessionState) -> list[dict[str, Any]]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if state.plan:
        messages.append({"role": "system", "content": "Current plan: " + str(state.plan)})
    if state.summary:
        messages.append({"role": "system", "content": "Earlier session summary: " + state.summary})
    return [*messages, *state.messages]

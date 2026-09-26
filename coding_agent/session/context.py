"""Build model context from a session's conversation."""

from typing import Any

from coding_agent.session.state import SessionState


SYSTEM_PROMPT = (
    "You are a coding agent working in /workspace. Use the available tools to "
    "inspect and modify the repository. Give a final reply when you are done."
)


def build_context(state: SessionState) -> list[dict[str, Any]]:
    return [{"role": "system", "content": SYSTEM_PROMPT}, *state.messages]

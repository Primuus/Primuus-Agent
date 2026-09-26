"""Build model-independent conversation context from run state."""

from dataclasses import asdict
import json

from coding_agent.harness.state import RunState
from coding_agent.harness.task import LoadedTask


SYSTEM_PROMPT = (
    "You are a coding agent working in /workspace. Use the available tools to "
    "inspect and modify the repository. Give a final reply when you are done."
)


def build_context(task: LoadedTask, state: RunState) -> list[dict[str, str]]:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task.instructions},
    ]
    for turn in state.turns:
        call = turn.response.tool_call
        if call is None:
            messages.append({"role": "assistant", "content": turn.response.final_message or ""})
        else:
            messages.append(
                {"role": "assistant", "content": json.dumps({"tool_call": asdict(call)})}
            )
            messages.append(
                {"role": "tool", "content": json.dumps(asdict(turn.result))}
            )
    return messages

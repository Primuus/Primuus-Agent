"""Build model-independent conversation context from run state."""

from dataclasses import asdict
import json
from typing import Any

from coding_agent.harness.state import RunState
from coding_agent.harness.task import LoadedTask


SYSTEM_PROMPT = (
    "You are a coding agent working in /workspace. Use the available tools to "
    "inspect and modify the repository. Give a final reply when you are done."
)


def build_context(task: LoadedTask, state: RunState) -> list[dict[str, Any]]:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task.instructions},
    ]
    for turn in state.turns:
        if not turn.response.tool_calls:
            messages.append({"role": "assistant", "content": turn.response.final_message or ""})
        else:
            messages.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": call.call_id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(call.arguments),
                        },
                    } for call in turn.response.tool_calls],
                }
            )
            for result, _ in turn.observations:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": result.call_id,
                        "content": json.dumps(asdict(result)),
                    }
                )
    return messages

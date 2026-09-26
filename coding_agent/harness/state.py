"""Mutable state for one task run."""

from dataclasses import dataclass, field

from coding_agent.contracts import ModelResponse, StopReason, ToolResult


@dataclass(frozen=True)
class Turn:
    response: ModelResponse
    result: ToolResult | None = None


@dataclass
class RunState:
    task_id: str
    steps: int = 0
    turns: list[Turn] = field(default_factory=list)
    stop_reason: StopReason | None = None
    tokens: int | None = 0

    @property
    def success(self) -> bool:
        return self.stop_reason == "verified"

    @property
    def tool_calls(self) -> int:
        return sum(turn.response.tool_call is not None for turn in self.turns)

    @property
    def failed_tool_calls(self) -> int:
        return sum(
            turn.result is not None
            and (turn.result.status != "completed" or turn.result.exit_code not in (None, 0))
            for turn in self.turns
        )

    def add_turn(self, response: ModelResponse, result: ToolResult | None = None) -> None:
        self.steps += 1
        self.turns.append(Turn(response, result))
        if response.input_tokens is None or response.output_tokens is None:
            self.tokens = None
        elif self.tokens is not None:
            self.tokens += response.input_tokens + response.output_tokens

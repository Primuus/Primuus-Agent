"""File and shell tools executed through the task container."""

import subprocess
from time import monotonic

from coding_agent.contracts import ToolCall, ToolResult
from coding_agent.sandbox.docker import DockerSandbox


READ_SCRIPT = (
    "from pathlib import Path; import sys; "
    "sys.stdout.write(Path(sys.argv[1]).read_text(encoding='utf-8'))"
)
WRITE_SCRIPT = (
    "from pathlib import Path; import sys; "
    "p = Path(sys.argv[1]); p.parent.mkdir(parents=True, exist_ok=True); "
    "p.write_text(sys.stdin.read(), encoding='utf-8')"
)


class DockerTools:
    def __init__(self, sandbox: DockerSandbox) -> None:
        self.sandbox = sandbox

    def execute(self, call: ToolCall) -> ToolResult:
        started = monotonic()
        expected = {
            "read_file": {"path"},
            "write_file": {"path", "content"},
            "run_shell": {"command"},
        }
        if call.name not in expected or set(call.arguments) != expected[call.name]:
            return self._error(call, "Invalid tool name or arguments", started)
        if not all(type(value) is str for value in call.arguments.values()):
            return self._error(call, "Tool arguments must be strings", started)
        try:
            if call.name == "read_file":
                path = self.sandbox.relative_path(call.arguments["path"])
                completed = self.sandbox.exec(["python", "-c", READ_SCRIPT, path])
            elif call.name == "write_file":
                path = self.sandbox.relative_path(call.arguments["path"])
                completed = self.sandbox.exec(
                    ["python", "-c", WRITE_SCRIPT, path], call.arguments["content"]
                )
            else:
                completed = self.sandbox.exec(
                    [
                        "timeout", "--kill-after=1s",
                        f"{self.sandbox.tool_timeout_seconds}s",
                        "sh", "-lc", call.arguments["command"],
                    ]
                )
        except ValueError as error:
            return self._error(call, str(error), started)
        except subprocess.TimeoutExpired:
            return ToolResult(
                call.call_id, call.name, "timeout", "", "Tool timed out", None,
                int((monotonic() - started) * 1000),
            )

        duration = int((monotonic() - started) * 1000)
        if call.name == "run_shell":
            status = "timeout" if completed.returncode == 124 else "completed"
            return ToolResult(
                call.call_id, call.name, status, completed.stdout,
                completed.stderr or None, completed.returncode, duration,
            )
        return ToolResult(
            call.call_id, call.name,
            "completed" if completed.returncode == 0 else "error",
            completed.stdout,
            completed.stderr or None,
            None,
            duration,
        )

    @staticmethod
    def _error(call: ToolCall, message: str, started: float) -> ToolResult:
        return ToolResult(
            call.call_id, call.name, "error", "", message, None,
            int((monotonic() - started) * 1000),
        )

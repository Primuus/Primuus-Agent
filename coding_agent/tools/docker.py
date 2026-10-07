"""Repository tools executed inside an isolated Docker workspace."""

import json
import subprocess
from time import monotonic

from coding_agent.contracts import ToolCall, ToolResult
from coding_agent.session.workspace import Workspace


READ_SCRIPT = (
    "from pathlib import Path; import sys; "
    "sys.stdout.write(Path(sys.argv[1]).read_text(encoding='utf-8'))"
)
WRITE_SCRIPT = (
    "from pathlib import Path; import sys; "
    "p = Path(sys.argv[1]); p.parent.mkdir(parents=True, exist_ok=True); "
    "p.write_text(sys.stdin.read(), encoding='utf-8')"
)
RANGE_SCRIPT = """from pathlib import Path
import sys
lines = Path(sys.argv[1]).read_text(encoding='utf-8').splitlines()
start, end = int(sys.argv[2]), int(sys.argv[3])
for number in range(start, min(end, len(lines)) + 1):
    print(f'{number}: {lines[number - 1]}')
"""
LIST_SCRIPT = """import subprocess
files = subprocess.check_output(['git', 'ls-files', '-co', '--exclude-standard'], text=True)
for path in sorted(files.splitlines())[:300]:
    print(path)
"""
SEARCH_SCRIPT = """from pathlib import Path
from fnmatch import fnmatch
import subprocess
import sys
query = sys.argv[1]
scope = Path(sys.argv[2])
pattern = sys.argv[3]
found = 0
files = subprocess.check_output(['git', 'ls-files', '-co', '--exclude-standard'], text=True)
for name in sorted(files.splitlines()):
    path = Path(name)
    if path != scope and scope not in path.parents:
        continue
    if pattern and not (fnmatch(name, pattern) or fnmatch(path.name, pattern)):
        continue
    if not path.is_file():
        continue
    try:
        lines = path.read_text(encoding='utf-8').splitlines()
    except UnicodeDecodeError:
        continue
    for number, line in enumerate(lines, 1):
        if query in line:
            print(f'{path}:{number}:{line}')
            found += 1
            if found >= 100:
                raise SystemExit
"""
EDIT_SCRIPT = """from pathlib import Path
import json
import sys
path = Path(sys.argv[1])
edit = json.load(sys.stdin)
content = path.read_text(encoding='utf-8')
if not edit['old_text'] or content.count(edit['old_text']) != 1:
    raise SystemExit('old_text must match exactly once')
path.write_text(content.replace(edit['old_text'], edit['new_text'], 1), encoding='utf-8')
"""


class DockerTools:
    def __init__(self, sandbox: Workspace, base_commit: str | None = None) -> None:
        self.sandbox = sandbox
        self.base_commit = base_commit

    def execute(self, call: ToolCall) -> ToolResult:
        started = monotonic()
        expected = {
            "read_file": {"path"},
            "write_file": {"path", "content"},
            "run_shell": {"command"},
            "read_file_range": {"path", "start_line", "end_line"},
            "list_files": set(),
            "search_text": {"query", "path", "include"},
            "edit_file": {"path", "old_text", "new_text"},
            "git_status": set(),
            "git_diff": set(),
        }
        if call.name not in expected:
            return self._error(call, "Invalid tool name or arguments", started)
        required = {"query"} if call.name == "search_text" else expected[call.name]
        if not required <= set(call.arguments) <= expected[call.name]:
            return self._error(call, "Invalid tool name or arguments", started)
        if call.name == "read_file_range":
            arguments = call.arguments
            if (type(arguments["path"]) is not str
                or type(arguments["start_line"]) is not int
                or type(arguments["end_line"]) is not int
                or arguments["start_line"] < 1
                or arguments["end_line"] < arguments["start_line"]):
                return self._error(call, "Invalid line range", started)
        elif not all(type(value) is str for value in call.arguments.values()):
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
            elif call.name == "read_file_range":
                path = self.sandbox.relative_path(call.arguments["path"])
                completed = self.sandbox.exec([
                    "python", "-c", RANGE_SCRIPT, path,
                    str(call.arguments["start_line"]), str(call.arguments["end_line"]),
                ])
            elif call.name == "list_files":
                completed = self.sandbox.exec(["python", "-c", LIST_SCRIPT])
            elif call.name == "search_text":
                path = self.sandbox.relative_path(call.arguments.get("path", "."))
                completed = self.sandbox.exec([
                    "python", "-c", SEARCH_SCRIPT, call.arguments["query"],
                    path, call.arguments.get("include", ""),
                ])
            elif call.name == "edit_file":
                path = self.sandbox.relative_path(call.arguments["path"])
                completed = self.sandbox.exec(
                    ["python", "-c", EDIT_SCRIPT, path],
                    json.dumps({
                        "old_text": call.arguments["old_text"],
                        "new_text": call.arguments["new_text"],
                    }),
                )
            elif call.name == "git_status":
                completed = self.sandbox.exec(["git", "status", "--short"])
            elif call.name == "git_diff":
                completed = self.sandbox.exec(["git", "diff", self.base_commit or "HEAD", "--"])
            else:
                completed = self.sandbox.exec([
                    "timeout", "--kill-after=1s",
                    f"{self.sandbox.tool_timeout_seconds}s",
                    "sh", "-lc", call.arguments["command"],
                ])
        except ValueError as error:
            return self._error(call, str(error), started)
        except subprocess.TimeoutExpired:
            return ToolResult(
                call.call_id, call.name, "timeout", "", "Tool timed out", None,
                int((monotonic() - started) * 1000),
            )
        duration = int((monotonic() - started) * 1000)
        output = completed.stdout
        status = "timeout" if completed.returncode == 124 else "completed"
        if call.name != "run_shell" and completed.returncode != 0:
            status = "error"
        return ToolResult(
            call.call_id, call.name, status, output,
            completed.stderr or None,
            completed.returncode if call.name == "run_shell" else None,
            duration,
        )

    @staticmethod
    def _error(call: ToolCall, message: str, started: float) -> ToolResult:
        return ToolResult(
            call.call_id, call.name, "error", "", message, None,
            int((monotonic() - started) * 1000),
        )

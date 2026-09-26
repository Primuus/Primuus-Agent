"""Execution boundary required by repository tools."""

import subprocess
from pathlib import Path
from typing import Protocol


class Workspace(Protocol):
    workspace: Path
    tool_timeout_seconds: int

    def exec(
        self, command: list[str], input_text: str | None = None
    ) -> subprocess.CompletedProcess[str]: ...

    def relative_path(self, path: str) -> str: ...

"""Persistent, isolated Git workspace for a coding session."""

from dataclasses import dataclass
from pathlib import Path
import subprocess


@dataclass(frozen=True)
class RepositoryWorkspace:
    source: Path
    session_dir: Path
    workspace: Path
    base_commit: str

    @classmethod
    def create(cls, source: Path, session_dir: Path) -> "RepositoryWorkspace":
        root = Path(subprocess.run(
            ["git", "-C", str(source), "rev-parse", "--show-toplevel"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()).resolve()
        session_dir.mkdir(parents=True)
        workspace = session_dir / "workspace"
        subprocess.run(
            ["git", "clone", "--no-hardlinks", "--quiet", "--", str(root), str(workspace)],
            check=True, capture_output=True, text=True,
        )
        base = subprocess.run(
            ["git", "-C", str(workspace), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        return cls(root, session_dir, workspace, base)

    def status(self) -> str:
        return subprocess.run(
            ["git", "-C", str(self.workspace), "status", "--short"],
            check=True, capture_output=True, text=True,
        ).stdout

    def diff(self) -> str:
        subprocess.run(
            ["git", "-C", str(self.workspace), "add", "-N", "--all"],
            check=True, capture_output=True, text=True,
        )
        return subprocess.run(
            ["git", "-C", str(self.workspace), "diff", "--no-ext-diff", self.base_commit, "--"],
            check=True, capture_output=True, text=True,
        ).stdout

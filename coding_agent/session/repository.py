"""Persistent, isolated Git workspace for a coding session."""

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
from uuid import uuid4


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
        session_dir.mkdir(parents=True, mode=0o700)
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

    def snapshot(self, label: str) -> str:
        index = self.session_dir / f"snapshot-{uuid4().hex}.index"
        environment = {
            **os.environ,
            "GIT_INDEX_FILE": str(index),
            "GIT_AUTHOR_NAME": "Primuus Agent",
            "GIT_AUTHOR_EMAIL": "agent@localhost",
            "GIT_COMMITTER_NAME": "Primuus Agent",
            "GIT_COMMITTER_EMAIL": "agent@localhost",
        }
        try:
            subprocess.run(
                ["git", "-C", str(self.workspace), "read-tree", "HEAD"],
                check=True, capture_output=True, text=True, env=environment,
            )
            subprocess.run(
                ["git", "-C", str(self.workspace), "add", "-A"],
                check=True, capture_output=True, text=True, env=environment,
            )
            tree = subprocess.run(
                ["git", "-C", str(self.workspace), "write-tree"],
                check=True, capture_output=True, text=True, env=environment,
            ).stdout.strip()
            commit = subprocess.run(
                ["git", "-C", str(self.workspace), "commit-tree", tree, "-p", "HEAD", "-m", label],
                check=True, capture_output=True, text=True, env=environment,
            ).stdout.strip()
            subprocess.run(
                ["git", "-C", str(self.workspace), "update-ref", f"refs/agent/snapshots/{uuid4().hex}", commit],
                check=True, capture_output=True, text=True,
            )
            return commit
        finally:
            index.unlink(missing_ok=True)

    def restore(self, commit: str) -> None:
        subprocess.run(
            ["git", "-C", str(self.workspace), "reset", "--hard", commit],
            check=True, capture_output=True, text=True,
        )
        subprocess.run(
            ["git", "-C", str(self.workspace), "clean", "-fd"],
            check=True, capture_output=True, text=True,
        )

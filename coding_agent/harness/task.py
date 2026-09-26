"""Load a task bundle without starting its sandbox."""

import json
from dataclasses import dataclass
from pathlib import Path

from coding_agent.contracts import TaskSpec, VerifierSpec


@dataclass(frozen=True)
class LoadedTask:
    path: Path
    spec: TaskSpec
    instructions: str

    @property
    def repository(self) -> Path:
        return self.path / "repo"

    @property
    def verifier(self) -> Path:
        return self.path / self.spec.verifier.entrypoint


def load_task(path: Path) -> LoadedTask:
    path = path.resolve()
    manifest = json.loads((path / "task.json").read_text(encoding="utf-8"))
    if manifest["schema_version"] != 1 or manifest["task_id"] != path.name:
        raise ValueError(f"Invalid task manifest: {path}")
    spec = TaskSpec(
        schema_version=manifest["schema_version"],
        task_id=manifest["task_id"],
        title=manifest["title"],
        tags=manifest["tags"],
        verifier=VerifierSpec(**manifest["verifier"]),
    )
    return LoadedTask(path, spec, (path / "task.md").read_text(encoding="utf-8"))

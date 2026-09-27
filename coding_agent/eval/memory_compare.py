"""Paired repository-session comparison of memory context strategies."""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from shutil import copyfile
from statistics import mean
from typing import Callable

from coding_agent.models.base import ModelBackend
from coding_agent.session.app import RepositorySession
from coding_agent.session.memory import MemoryStore, repository_identity


MEMORY_MODES = ("off", "summary", "retrieve")


def compare_memory(
    source: Path, task: str, checks: list[str], config: dict,
    make_model: Callable[[], ModelBackend], sessions_dir: Path,
    output_dir: Path, repeats: int,
) -> dict:
    if repeats < 1 or not checks:
        raise ValueError("Memory comparison needs at least one repeat and one project check")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("Memory comparison output directory must be empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    repository, base_commit = repository_identity(source)
    memory_snapshot = MemoryStore(Path(config["memory_dir"])).snapshot_to(output_dir / "memory")
    snapshot_digest = sha256(memory_snapshot.read_bytes()).hexdigest()
    runs = []
    model_id = None

    for repeat in range(1, repeats + 1):
        for mode in MEMORY_MODES:
            variant_config = deepcopy(config)
            variant_config["memory"] = {**config["memory"], "mode": mode, "capture": False}
            variant_config["memory_dir"] = str(memory_snapshot.parent)
            model = make_model()
            if model_id is None:
                model_id = model.model_id
            elif model.model_id != model_id:
                raise ValueError("Memory comparison requires the same model for every variant")
            session = RepositorySession.create(
                source, sessions_dir, model, variant_config, "auto",
            )
            if session.repository.base_commit != base_commit:
                raise RuntimeError("Repository HEAD changed during memory comparison")
            result = session.run(task, checks)
            success = result["stop_reason"] == "completed" and all(
                check["status"] == "completed" and check["exit_code"] == 0
                for check in result["checks"]
            )
            artifact_dir = output_dir / f"repeat-{repeat:03d}" / mode
            artifact_dir.mkdir(parents=True)
            for name in ("session.json", "result.json", "trace.jsonl", "diff.patch", "status.txt"):
                copyfile(session.repository.session_dir / name, artifact_dir / name)
            runs.append({
                "repeat": repeat, "mode": mode, "session_id": result["session_id"],
                "success": success, "stop_reason": result["stop_reason"],
                "steps": result["steps"], "tool_calls": result["tool_calls"],
                "tokens": result["tokens"], "active_seconds": result["active_seconds"],
                "memory_ids": result["memory_ids"],
                "artifact_dir": str(artifact_dir),
            })

    aggregates = {}
    for mode in MEMORY_MODES:
        selected = [run for run in runs if run["mode"] == mode]
        tokens = [run["tokens"] for run in selected if run["tokens"] is not None]
        aggregates[mode] = {
            "runs": len(selected),
            "successes": sum(run["success"] for run in selected),
            "success_rate": sum(run["success"] for run in selected) / len(selected),
            "mean_steps": round(mean(run["steps"] for run in selected), 3),
            "mean_tool_calls": round(mean(run["tool_calls"] for run in selected), 3),
            "mean_tokens": round(mean(tokens), 3) if tokens else None,
            "mean_active_seconds": round(mean(run["active_seconds"] for run in selected), 3),
        }
    report = {
        "schema_version": 1, "source_repository": repository,
        "base_commit": base_commit, "task": task, "checks": checks,
        "model": config["model"], "model_id": model_id, "repeats": repeats,
        "memory_snapshot": str(memory_snapshot),
        "memory_sha256": snapshot_digest,
        "runs": runs, "aggregates": aggregates,
    }
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return report

"""Independent coding sessions with reviewable task handoffs and patch integration."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from shutil import copyfile
import subprocess
from typing import Callable

from coding_agent.contracts import ToolCall
from coding_agent.models.base import ModelBackend
from coding_agent.sandbox.docker import DockerSandbox
from coding_agent.session.app import RepositorySession
from coding_agent.session.memory import MemoryStore, repository_identity
from coding_agent.session.repository import RepositoryWorkspace
from coding_agent.tools.docker import DockerTools


def _valid_path(path: str) -> bool:
    supplied = Path(path)
    return bool(path) and not supplied.is_absolute() and ".." not in supplied.parts


def _within_scope(path: str, scopes: list[str]) -> bool:
    return any(path == scope.rstrip("/") or path.startswith(scope.rstrip("/") + "/")
               for scope in scopes)


def validate_manifest(manifest: dict) -> None:
    if type(manifest) is not dict or set(manifest) != {"tasks", "integration_checks"}:
        raise ValueError("Parallel manifest needs tasks and integration_checks")
    tasks = manifest["tasks"]
    checks = manifest["integration_checks"]
    if (type(tasks) is not list or len(tasks) < 2 or type(checks) is not list
        or not checks or any(type(check) is not str or not check for check in checks)):
        raise ValueError("Parallel manifest needs at least two tasks and integration checks")
    identifiers = []
    for task in tasks:
        if (type(task) is not dict or set(task) != {"id", "instruction", "paths", "checks"}
            or any(type(task[key]) is not str or not task[key] for key in ("id", "instruction"))
            or not task["id"].replace("-", "").replace("_", "").isalnum()
            or type(task["paths"]) is not list or not task["paths"]
            or any(type(path) is not str or not _valid_path(path) for path in task["paths"])
            or type(task["checks"]) is not list or not task["checks"]
            or any(type(check) is not str or not check for check in task["checks"])):
            raise ValueError("Each parallel task needs an id, instruction, paths and checks")
        identifiers.append(task["id"])
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Parallel task ids must be unique")


def run_parallel(
    source: Path, manifest: dict, config: dict,
    make_model: Callable[[], ModelBackend], sessions_dir: Path,
    output_dir: Path, workers: int, approval_mode: str = "auto",
) -> dict:
    validate_manifest(manifest)
    if workers < 1 or approval_mode == "ask":
        raise ValueError("Parallel sessions need workers >= 1 and non-interactive approval")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("Parallel output directory must be empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    repository, base_commit = repository_identity(source)
    task_config = deepcopy(config)
    task_config["memory"] = {**config["memory"], "capture": False}
    memory_snapshot = None
    if task_config["memory"]["mode"] != "off":
        memory_snapshot = MemoryStore(Path(config["memory_dir"])).snapshot_to(output_dir / "memory")
        task_config["memory_dir"] = str(memory_snapshot.parent)
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )

    assignments = []
    for task in manifest["tasks"]:
        session = RepositorySession.create(
            source, sessions_dir, make_model(), deepcopy(task_config), approval_mode,
        )
        if session.repository.base_commit != base_commit:
            raise RuntimeError("Repository HEAD changed while creating parallel sessions")
        assignments.append((task, session))

    def execute_assignment(assignment: tuple[dict, RepositorySession]) -> dict:
        task, session = assignment
        directory = output_dir / "tasks" / task["id"]
        directory.mkdir(parents=True)
        instruction = (
            f"{task['instruction']}\nOnly change these assigned paths: "
            + ", ".join(task["paths"])
        )
        error = None
        result = None
        try:
            result = session.run(instruction, task["checks"])
        except Exception as caught:
            error = f"{type(caught).__name__}: {caught}"
        changed_paths = session.repository.changed_files()
        outside_scope = [path for path in changed_paths
                         if not _within_scope(path, task["paths"])]
        for name in ("session.json", "result.json", "trace.jsonl", "diff.patch", "status.txt"):
            source_file = session.repository.session_dir / name
            if source_file.is_file():
                copyfile(source_file, directory / name)
        success = bool(
            result is not None and result["stop_reason"] == "completed"
            and all(check["status"] == "completed" and check["exit_code"] == 0
                    for check in result["checks"])
            and not outside_scope
        )
        handoff = {
            "task_id": task["id"], "instruction": task["instruction"],
            "paths": task["paths"], "checks": task["checks"],
            "check_results": result["checks"] if result else [],
            "session_id": session.session_id, "base_commit": base_commit,
            "changed_paths": changed_paths, "outside_scope": outside_scope,
            "success": success, "stop_reason": result["stop_reason"] if result else None,
            "error": error, "artifact_dir": str(directory),
            "diff_path": str(directory / "diff.patch"),
            "trace_path": str(directory / "trace.jsonl"),
        }
        (directory / "handoff.json").write_text(
            json.dumps(handoff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
        return handoff

    with ThreadPoolExecutor(max_workers=workers) as pool:
        handoffs = list(pool.map(execute_assignment, assignments))

    integration = RepositoryWorkspace.create(source, output_dir / "integration")
    if integration.base_commit != base_commit:
        raise RuntimeError("Repository HEAD changed before patch integration")
    applications = []
    for handoff in handoffs:
        patch = Path(handoff["artifact_dir"]) / "diff.patch"
        if not handoff["success"]:
            applications.append({"task_id": handoff["task_id"], "status": "skipped"})
        elif not patch.read_text(encoding="utf-8"):
            applications.append({"task_id": handoff["task_id"], "status": "no_changes"})
        else:
            checked = subprocess.run(
                ["git", "-C", str(integration.workspace), "apply", "--check", str(patch)],
                capture_output=True, text=True,
            )
            if checked.returncode != 0:
                applications.append({
                    "task_id": handoff["task_id"], "status": "conflict",
                    "error": checked.stderr.strip(),
                })
            else:
                subprocess.run(
                    ["git", "-C", str(integration.workspace), "apply", str(patch)],
                    check=True, capture_output=True, text=True,
                )
                applications.append({"task_id": handoff["task_id"], "status": "applied"})

    sandbox_config = config["sandbox"]
    check_results = []
    with DockerSandbox(
        integration.workspace, sandbox_config["image"], sandbox_config["cpus"],
        sandbox_config["memory_mb"], sandbox_config["network_enabled"],
        config["tool_timeout_seconds"],
    ) as sandbox:
        tools = DockerTools(sandbox, integration.base_commit)
        for index, command in enumerate(manifest["integration_checks"], 1):
            result = tools.execute(ToolCall(f"integration-{index}", "run_shell", {"command": command}))
            check_results.append({
                "command": command, "status": result.status,
                "exit_code": result.exit_code, "output": result.output,
                "error": result.error,
            })
    (integration.session_dir / "diff.patch").write_text(integration.diff(), encoding="utf-8")
    (integration.session_dir / "status.txt").write_text(integration.status(), encoding="utf-8")
    integration_success = (
        all(handoff["success"] for handoff in handoffs)
        and all(application["status"] in ("applied", "no_changes") for application in applications)
        and all(check["status"] == "completed" and check["exit_code"] == 0
                for check in check_results)
    )
    report = {
        "schema_version": 1, "source_repository": repository,
        "base_commit": base_commit, "model": config["model"],
        "workers": workers, "memory_snapshot_sha256": (
            sha256(memory_snapshot.read_bytes()).hexdigest() if memory_snapshot else None
        ),
        "tasks": handoffs,
        "integration": {
            "success": integration_success,
            "workspace": str(integration.workspace),
            "applications": applications,
            "checks": check_results,
            "diff_path": str(integration.session_dir / "diff.patch"),
            "status_path": str(integration.session_dir / "status.txt"),
        },
    }
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return report

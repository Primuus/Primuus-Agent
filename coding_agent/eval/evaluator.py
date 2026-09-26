"""Run tasks and save reproducible traces and aggregate results."""

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from uuid import uuid4

from coding_agent.contracts import RunResult
from coding_agent.harness.runner import Runner
from coding_agent.harness.task import load_task
from coding_agent.models.base import ModelBackend
from coding_agent.sandbox.docker import DockerSandbox
from coding_agent.tools.docker import DockerTools
from coding_agent.verifier.docker import DockerVerifier


def task_digest(task_path: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(task_path.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        digest.update(str(path.relative_to(task_path)).encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def run_task(
    task_path: Path,
    model: ModelBackend,
    config: dict,
    results_dir: Path,
) -> RunResult:
    task = load_task(task_path)
    run_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{task.spec.task_id}-{uuid4().hex[:8]}"
    run_dir = results_dir / run_id
    run_dir.mkdir(parents=True)
    started = monotonic()
    sandbox_config = config["sandbox"]
    with DockerSandbox(
        task.repository,
        sandbox_config["image"],
        sandbox_config["cpus"],
        sandbox_config["memory_mb"],
        sandbox_config["network_enabled"],
        config["tool_timeout_seconds"],
    ) as sandbox:
        verifier = DockerVerifier(
            task, sandbox.workspace, sandbox_config["image"],
            sandbox_config["cpus"], sandbox_config["memory_mb"],
            config["verifier_timeout_seconds"],
        )
        state = Runner(
            model, DockerTools(sandbox).execute, verifier.check,
            config["max_steps"], config["task_timeout_seconds"],
        ).run(task)
    result = RunResult(
        run_id=run_id,
        task_id=task.spec.task_id,
        model_id=model.model_id,
        success=state.success,
        stop_reason=state.stop_reason,
        steps=state.steps,
        tool_calls=state.tool_calls,
        failed_tool_calls=state.failed_tool_calls,
        retries=0,
        tokens=state.tokens,
        latency_seconds=round(monotonic() - started, 3),
        trace_path=str(run_dir / "trace.jsonl"),
    )
    write_trace(run_dir / "trace.jsonl", result, state.turns)
    (run_dir / "result.json").write_text(
        json.dumps(asdict(result), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (run_dir / "config.json").write_text(
        json.dumps(
            {"config": config, "task_digest": task_digest(task.path)},
            ensure_ascii=False, indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    return result


def write_trace(path: Path, result: RunResult, turns: list) -> None:
    events = []
    for index, turn in enumerate(turns, 1):
        events.append({
            "run_id": result.run_id,
            "step": index,
            "event_type": "model_action",
            "timestamp": turn.model_at,
            "data": {
                "response": asdict(turn.response),
                "duration_ms": turn.model_duration_ms,
            },
        })
        for tool_result, tool_at in turn.observations:
            events.append({
                "run_id": result.run_id,
                "step": index,
                "event_type": "tool_result",
                "timestamp": tool_at,
                "data": asdict(tool_result),
            })
        if turn.verification is not None:
            events.append({
                "run_id": result.run_id,
                "step": index,
                "event_type": "verification_result",
                "timestamp": turn.verification_at,
                "data": asdict(turn.verification),
            })
    events.append({
        "run_id": result.run_id,
        "step": result.steps,
        "event_type": "task_finished",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {"success": result.success, "stop_reason": result.stop_reason},
    })
    path.write_text(
        "\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n",
        encoding="utf-8",
    )


def run_batch(
    task_paths: list[Path],
    make_model,
    config: dict,
    results_dir: Path,
) -> dict:
    results = [run_task(path, make_model(), config, results_dir) for path in task_paths]
    count = len(results)
    summary = {
        "task_count": count,
        "success_count": sum(result.success for result in results),
        "success_rate": sum(result.success for result in results) / count,
        "avg_steps": sum(result.steps for result in results) / count,
        "avg_tool_calls": sum(result.tool_calls for result in results) / count,
        "avg_latency_seconds": sum(result.latency_seconds for result in results) / count,
        "runs": [result.run_id for result in results],
    }
    summary_path = results_dir / f"batch-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return summary

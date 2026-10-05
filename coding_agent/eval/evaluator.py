"""Run tasks and save reproducible traces and aggregate results."""

import hashlib
import json
import re
import subprocess
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from uuid import uuid4
from copy import deepcopy

from coding_agent.contracts import RunResult
from coding_agent.harness.task import load_task
from coding_agent.models.base import ModelBackend
from coding_agent.sandbox.docker import DockerSandbox
from coding_agent.session.runner import SessionRunner
from coding_agent.session.recovery import RecoveryPolicy
from coding_agent.session.state import SessionSpec, SessionState
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


def evaluation_patch(source: Path, workspace: Path) -> str:
    diff = subprocess.run(
        [
            "git", "diff", "--no-index", "--binary", "--no-ext-diff",
            "--src-prefix=a/", "--dst-prefix=b/", str(source), str(workspace),
        ],
        capture_output=True, text=True,
    )
    if diff.returncode not in (0, 1):
        raise RuntimeError(diff.stderr)
    source_prefix = str(source.resolve()).lstrip("/")
    workspace_prefix = str(workspace.resolve()).lstrip("/")
    patch = diff.stdout.replace(f"a/{source_prefix}/", "a/")
    patch = patch.replace(f"b/{workspace_prefix}/", "b/")
    patch = patch.replace(f"a/{workspace_prefix}/", "a/")
    patch = patch.replace(f"b/{source_prefix}/", "b/")
    blocks = []
    for block in re.split(r"(?=^diff --git )", patch, flags=re.MULTILINE):
        if not block:
            continue
        header = block.split("\n", 1)[0]
        if "/.pytest_cache/" in header or "/__pycache__/" in header or header.endswith((".pyc", '.pyc"')):
            continue
        blocks.append(block)
    return "".join(blocks)


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
        state = SessionRunner(
            model, DockerTools(sandbox).execute, verifier.check,
            config["max_steps"], config["task_timeout_seconds"],
            max_tokens=config["max_tokens"],
            context_max_chars=config["context_max_chars"],
            context_keep_messages=config["context_keep_messages"],
            context_tool_output_chars=config.get("context_tool_output_chars", 4000),
            recovery=RecoveryPolicy.from_config(config),
        ).run(SessionSpec(run_id, task.instructions))
        patch = evaluation_patch(task.repository, sandbox.workspace)
        (run_dir / "diff.patch").write_text(patch, encoding="utf-8")
        checks = [turn.verification for turn in state.turns if turn.verification is not None]
        (run_dir / "verification.json").write_text(
            json.dumps(
                {"count": len(checks), "final": asdict(checks[-1]) if checks else None},
                ensure_ascii=False, indent=2,
            ) + "\n",
            encoding="utf-8",
        )
    failure_counts: dict[str, int] = {}
    for event in state.events:
        if event["event_type"] == "failure_detected":
            category = event["data"]["category"]
            failure_counts[category] = failure_counts.get(category, 0) + 1
    recovery_actions = [
        event["data"]["kind"] for event in state.events
        if event["event_type"] == "recovery_action"
    ]
    result = RunResult(
        run_id=run_id,
        task_id=task.spec.task_id,
        model_id=model.model_id,
        success=state.success,
        stop_reason=state.stop_reason,
        steps=state.steps,
        tool_calls=state.tool_calls,
        failed_tool_calls=state.failed_tool_calls,
        retries=sum(kind in ("model_retry", "tool_retry", "validation_retry") for kind in recovery_actions),
        recoveries=sum(kind in ("model_retry", "tool_retry", "validation_retry", "snapshot_rollback", "alternative_action") for kind in recovery_actions),
        manual_interventions=0,
        failure_counts=failure_counts,
        tokens=state.tokens,
        latency_seconds=round(monotonic() - started, 3),
        trace_path=str(run_dir / "trace.jsonl"),
    )
    write_trace(run_dir / "trace.jsonl", state)
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


def write_trace(path: Path, state: SessionState) -> None:
    path.write_text(
        "\n".join(json.dumps(event, ensure_ascii=False) for event in state.events) + "\n",
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
        "total_tokens": (sum(result.tokens for result in results)
                         if all(result.tokens is not None for result in results) else None),
        "runs": [result.run_id for result in results],
    }
    summary_path = results_dir / f"batch-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return summary


def run_baseline(
    task_paths: list[Path], make_model, config: dict, output_dir: Path, repeats: int,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    report_path = output_dir / "report.json"
    fixed = {
        "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "config": config,
        "task_digests": {path.name: task_digest(path) for path in task_paths},
        "task_order": [path.name for path in task_paths],
        "repeats": repeats,
    }
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest != fixed:
            raise ValueError("Baseline manifest differs from the current code, tasks, or config")
        trials = json.loads(report_path.read_text(encoding="utf-8"))["trials"] if report_path.exists() else []
    else:
        if any(output_dir.iterdir()):
            raise ValueError("Baseline output directory must be empty")
        manifest_path.write_text(json.dumps(fixed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        trials = []

    completed = {(trial["task_id"], trial["repetition"]) for trial in trials}

    def summarize() -> dict:
        by_task = {}
        for path in task_paths:
            results = [trial["result"] for trial in trials if trial["task_id"] == path.name]
            by_task[path.name] = {
                "runs": len(results),
                "successes": sum(result["success"] for result in results),
                "stop_reasons": sorted({result["stop_reason"] for result in results}),
            }
        results = [trial["result"] for trial in trials]
        count = len(results)
        return {
            "status": "complete" if count == len(task_paths) * repeats else "running",
            "run_count": count,
            "planned_runs": len(task_paths) * repeats,
            "success_count": sum(result["success"] for result in results),
            "success_rate": sum(result["success"] for result in results) / count if count else None,
            "avg_steps": sum(result["steps"] for result in results) / count if count else None,
            "avg_tool_calls": sum(result["tool_calls"] for result in results) / count if count else None,
            "avg_failed_tool_calls": sum(result["failed_tool_calls"] for result in results) / count if count else None,
            "avg_tokens": (sum(result["tokens"] for result in results) / count
                           if count and all(result["tokens"] is not None for result in results) else None),
            "avg_latency_seconds": sum(result["latency_seconds"] for result in results) / count if count else None,
            "manual_interventions": sum(result["manual_interventions"] for result in results),
            "by_task": by_task,
            "trials": trials,
        }

    if not report_path.exists():
        report_path.write_text(json.dumps(summarize(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for repetition in range(1, repeats + 1):
        for path in task_paths:
            if (path.name, repetition) in completed:
                continue
            result = run_task(path, make_model(), config, output_dir / "records")
            run_id = result.run_id
            trials.append({
                "task_id": path.name,
                "repetition": repetition,
                "result": asdict(result),
                "artifacts": {
                    name: f"records/{run_id}/{name}"
                    for name in ("trace.jsonl", "diff.patch", "verification.json", "result.json", "config.json")
                },
            })
            report_path.write_text(json.dumps(summarize(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"{path.name} repeat {repetition}/{repeats}: {result.stop_reason} ",
                  f"steps={result.steps} tokens={result.tokens}", flush=True)
    return summarize()


def run_recovery_comparison(
    task_paths: list[Path], make_model, config: dict, output_dir: Path, repeats: int,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    report_path = output_dir / "report.json"
    fixed = {
        "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "base_config": config,
        "task_digests": {path.name: task_digest(path) for path in task_paths},
        "task_order": [path.name for path in task_paths],
        "repeats": repeats,
        "variant_order": "off/on for odd repetitions, on/off for even repetitions",
    }
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest != fixed:
            raise ValueError("Comparison manifest differs from the current code, tasks, or config")
        trials = json.loads(report_path.read_text(encoding="utf-8"))["trials"]
    else:
        if any(output_dir.iterdir()):
            raise ValueError("Comparison output directory must be empty")
        manifest_path.write_text(json.dumps(fixed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        trials = []

    def trace_metrics(path: Path) -> dict:
        events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        calls = [
            json.dumps((event["data"]["name"], event["data"]["arguments"]), sort_keys=True)
            for event in events if event["event_type"] == "tool_started"
        ]
        counts = Counter(calls)
        actions = Counter(
            event["data"]["kind"] for event in events
            if event["event_type"] == "recovery_action"
        )
        return {
            "repeated_tool_calls": sum(count - 1 for count in counts.values() if count > 1),
            "recovery_actions": dict(actions),
            "observed_turn_tokens": sum(
                (event["data"]["response"]["input_tokens"] or 0)
                + (event["data"]["response"]["output_tokens"] or 0)
                for event in events if event["event_type"] == "model_action"
            ),
            "unmeasured_model_requests": sum(
                event["event_type"] == "failure_detected" and event["data"]["category"] == "model_service"
                for event in events
            ),
        }

    def summarize() -> dict:
        variants = {}
        for variant in ("off", "on"):
            group = [trial for trial in trials if trial["variant"] == variant]
            results = [trial["result"] for trial in group]
            count = len(results)
            known_tokens = [result["tokens"] for result in results if result["tokens"] is not None]
            with_failures = [result for result in results if result["failure_counts"]]
            variants[variant] = {
                "runs": count,
                "successes": sum(result["success"] for result in results),
                "success_rate": sum(result["success"] for result in results) / count if count else None,
                "success_after_detected_failure": sum(result["success"] for result in with_failures),
                "runs_with_detected_failure": len(with_failures),
                "avg_steps": sum(result["steps"] for result in results) / count if count else None,
                "avg_tool_calls": sum(result["tool_calls"] for result in results) / count if count else None,
                "avg_failed_tool_calls": sum(result["failed_tool_calls"] for result in results) / count if count else None,
                "avg_repeated_tool_calls": sum(trial["trace_metrics"]["repeated_tool_calls"] for trial in group) / count if count else None,
                "avg_tokens": sum(known_tokens) / count if len(known_tokens) == count and count else None,
                "known_token_runs": len(known_tokens),
                "known_token_total": sum(known_tokens),
                "observed_turn_token_total": sum(trial["trace_metrics"]["observed_turn_tokens"] for trial in group),
                "unmeasured_model_requests": sum(trial["trace_metrics"]["unmeasured_model_requests"] for trial in group),
                "avg_latency_seconds": sum(result["latency_seconds"] for result in results) / count if count else None,
                "manual_interventions": sum(result["manual_interventions"] for result in results),
                "stop_reasons": dict(Counter(result["stop_reason"] for result in results)),
                "recovery_actions": dict(sum(
                    (Counter(trial["trace_metrics"]["recovery_actions"]) for trial in group), Counter()
                )),
            }
        matched = []
        for repetition in range(1, repeats + 1):
            for path in task_paths:
                pair = {
                    variant: next((trial for trial in trials if trial["task_id"] == path.name
                                   and trial["repetition"] == repetition and trial["variant"] == variant), None)
                    for variant in ("off", "on")
                }
                if all(pair.values()):
                    matched.append({
                        "task_id": path.name,
                        "repetition": repetition,
                        "off": {"run_id": pair["off"]["result"]["run_id"], "success": pair["off"]["result"]["success"]},
                        "on": {"run_id": pair["on"]["result"]["run_id"], "success": pair["on"]["result"]["success"]},
                    })
        return {
            "status": "complete" if len(trials) == 2 * repeats * len(task_paths) else "running",
            "run_count": len(trials),
            "planned_runs": 2 * repeats * len(task_paths),
            "completed_pairs": len(matched),
            "variants": variants,
            "pairs": matched,
            "trials": trials,
        }

    if not report_path.exists():
        report_path.write_text(json.dumps(summarize(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    completed = {(trial["task_id"], trial["repetition"], trial["variant"]) for trial in trials}
    for repetition in range(1, repeats + 1):
        for path in task_paths:
            order = ("off", "on") if repetition % 2 else ("on", "off")
            for variant in order:
                if (path.name, repetition, variant) in completed:
                    continue
                variant_config = deepcopy(config)
                variant_config["recovery"]["enabled"] = variant == "on"
                result = run_task(path, make_model(), variant_config, output_dir / "records")
                run_id = result.run_id
                trials.append({
                    "task_id": path.name,
                    "repetition": repetition,
                    "variant": variant,
                    "result": asdict(result),
                    "trace_metrics": trace_metrics(output_dir / "records" / run_id / "trace.jsonl"),
                    "artifacts": {
                        name: f"records/{run_id}/{name}"
                        for name in ("trace.jsonl", "diff.patch", "verification.json", "result.json", "config.json")
                    },
                })
                report_path.write_text(json.dumps(summarize(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                print(f"{path.name} repeat {repetition}/{repeats} {variant}: {result.stop_reason} ",
                      f"steps={result.steps} tokens={result.tokens}", flush=True)
    return summarize()


def compare_batch(
    task_paths: list[Path], make_model, config: dict, results_dir: Path, repeats: int,
) -> dict:
    results_dir.mkdir(parents=True, exist_ok=True)
    variants: dict[str, list[RunResult]] = {"baseline": [], "recovery": []}
    pairs = []
    for repetition in range(1, repeats + 1):
        for path in task_paths:
            outcomes = {}
            order = (("baseline", False), ("recovery", True))
            if repetition % 2 == 0:
                order = tuple(reversed(order))
            for name, enabled in order:
                variant_config = deepcopy(config)
                variant_config.setdefault("recovery", {})["enabled"] = enabled
                result = run_task(path, make_model(), variant_config, results_dir)
                variants[name].append(result)
                outcomes[name] = {"run_id": result.run_id, "success": result.success}
            pairs.append({"task_id": path.name, "repetition": repetition, **outcomes})

    def aggregate(results: list[RunResult]) -> dict:
        count = len(results)
        with_failures = [result for result in results if any(result.failure_counts.values())]
        return {
            "runs": count,
            "success_rate": sum(result.success for result in results) / count,
            "recovery_rate": (sum(result.success for result in with_failures) / len(with_failures)
                              if with_failures else None),
            "avg_steps": sum(result.steps for result in results) / count,
            "avg_tool_calls": sum(result.tool_calls for result in results) / count,
            "avg_failed_tool_calls": sum(result.failed_tool_calls for result in results) / count,
            "avg_recovery_actions": sum(result.recoveries for result in results) / count,
            "avg_tokens": (sum(result.tokens for result in results) / count
                           if all(result.tokens is not None for result in results) else None),
            "avg_latency_seconds": sum(result.latency_seconds for result in results) / count,
            "manual_interventions": sum(result.manual_interventions for result in results),
            "failure_counts": {
                category: sum(result.failure_counts.get(category, 0) for result in results)
                for category in sorted({name for result in results for name in result.failure_counts})
            },
            "run_ids": [result.run_id for result in results],
        }

    report = {
        "model_id": variants["baseline"][0].model_id,
        "task_digests": {path.name: task_digest(path) for path in task_paths},
        "repeats": repeats,
        "budget": {
            "max_steps": config["max_steps"],
            "task_timeout_seconds": config["task_timeout_seconds"],
            "tool_timeout_seconds": config["tool_timeout_seconds"],
            "verifier_timeout_seconds": config["verifier_timeout_seconds"],
        },
        "baseline": aggregate(variants["baseline"]),
        "recovery": aggregate(variants["recovery"]),
        "pairs": pairs,
    }
    if len({result.model_id for results in variants.values() for result in results}) != 1:
        raise ValueError("Comparison used different model IDs")
    path = results_dir / f"comparison-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report["report_path"] = str(path)
    return report

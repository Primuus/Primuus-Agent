"""Task evaluation and durable repository-session CLI."""

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
from shutil import copyfile
from urllib.parse import urlsplit

from coding_agent.eval.evaluator import compare_batch, run_baseline, run_batch, run_recovery_comparison, run_task
from coding_agent.eval.memory_compare import compare_memory
from coding_agent.eval.memory_series import compare_memory_series
from coding_agent.models.factory import create_model
from coding_agent.session.app import RepositorySession
from coding_agent.session.memory import MEMORY_KINDS, MemoryStore, repository_identity
from coding_agent.session.parallel import run_parallel


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the coding agent")
    parser.add_argument("command", choices=[
        "run", "batch", "baseline", "compare", "compare-recovery", "compare-memory", "compare-memory-series", "parallel", "exec", "ci", "chat", "resume", "inspect", "pause", "snapshot", "restore",
        "memory-add", "memory-list", "memory-update", "memory-remove", "memory-history",
    ])
    parser.add_argument("path", type=Path, help="Task path, Git repository, or session ID")
    parser.add_argument("--task", help="Instruction for exec, ci, chat, compare-memory, or resume")
    parser.add_argument("--check", action="append", help="Project check to run after execution")
    parser.add_argument("--approval-mode", choices=["auto", "ask", "read-only"])
    parser.add_argument("--sessions-dir", type=Path, default=Path.home() / ".local/state/primuus-agent/sessions")
    parser.add_argument("--output-dir", type=Path, help="CI, comparison, or parallel artifact directory")
    parser.add_argument("--tasks-file", type=Path, help="Parallel task handoff manifest")
    parser.add_argument("--workers", type=int, default=2, help="Concurrent repository sessions for parallel")
    parser.add_argument("--memory-dir", type=Path, help="Repository memory database directory")
    parser.add_argument("--memory-mode", choices=["off", "summary", "retrieve"], help="Memory context for a new session")
    parser.add_argument("--memory-id", help="Memory entry to update, remove, or inspect")
    parser.add_argument("--kind", choices=sorted(MEMORY_KINDS), help="Memory category")
    parser.add_argument("--text", help="Memory content")
    parser.add_argument("--source", help="Source reference for a manual memory revision")
    parser.add_argument("--scope", action="append", help="Relative repository path in memory scope")
    parser.add_argument("--all-memories", action="store_true", help="Include inactive memory entries")
    parser.add_argument("--max-steps", type=int)
    parser.add_argument("--repeats", type=int, default=1, help="Runs per task and variant for compare")
    parser.add_argument("--recovery-mode", choices=["on", "off"], help="Enable or disable automatic recovery")
    parser.add_argument("--model")
    parser.add_argument("--backend", choices=["openai_compatible", "anthropic"])
    parser.add_argument("--base-url")
    parser.add_argument("--api-key-env", help="Name of the environment variable containing the model key")
    parser.add_argument("--max-output-tokens", type=int)
    parser.add_argument("--instruction-file", action="append", help="Relative project instruction file")
    parser.add_argument("--skill", action="append", help="Repository skill name under .primuus/skills")
    parser.add_argument("--hooks-file", type=Path, help="JSON file defining before_tool and after_tool commands")
    parser.add_argument("--mcp-config", type=Path, help="JSON file with opt-in MCP stdio servers")
    parser.add_argument("--image", help="Docker image for the repository workspace")
    parser.add_argument("--network", action="store_true", help="Allow network access inside the repository container")
    parser.add_argument("--snapshot", help="Snapshot commit to restore")
    parser.add_argument("--resolve-pending", action="store_true", help="Acknowledge an interrupted tool after inspecting the workspace")
    parser.add_argument("--interactive", action="store_true", help="Stay in an interactive session after resume")
    parser.add_argument("--config", type=Path, default=Path("config/default.json"))
    arguments = parser.parse_args()
    default_memory_dir = Path.home() / ".local/state/primuus-agent/memory"
    if arguments.output_dir is not None and arguments.command not in ("baseline", "compare-recovery", "ci", "compare-memory", "compare-memory-series", "parallel"):
        parser.error("--output-dir is only available with baseline, compare-recovery, ci, compare-memory, compare-memory-series or parallel")
    if arguments.tasks_file is not None and arguments.command != "parallel":
        parser.error("--tasks-file is only available with parallel")
    config = json.loads(arguments.config.read_text(encoding="utf-8"))
    if arguments.command.startswith("memory-"):
        repository, commit = repository_identity(arguments.path)
        store = MemoryStore(arguments.memory_dir or default_memory_dir)
        source = {"kind": "manual", "ref": arguments.source or "", "commit": commit}
        if arguments.command == "memory-add":
            if not arguments.kind or not arguments.text or not arguments.source:
                parser.error("memory-add requires --kind, --text and --source")
            result = store.add(repository, arguments.kind, arguments.text, arguments.scope or [], source)
        elif arguments.command == "memory-list":
            result = [entry.to_dict() for entry in store.list(repository, not arguments.all_memories)]
        else:
            if not arguments.memory_id:
                parser.error(f"{arguments.command} requires --memory-id")
            if arguments.command == "memory-update":
                if not arguments.text or not arguments.source:
                    parser.error("memory-update requires --text and --source")
                previous = store.get(repository, arguments.memory_id)
                result = store.update(
                    repository, arguments.memory_id, arguments.text,
                    previous.scope if arguments.scope is None else arguments.scope, source,
                )
            elif arguments.command == "memory-remove":
                result = store.deactivate(repository, arguments.memory_id)
            else:
                result = store.history(repository, arguments.memory_id)
        print(json.dumps(result.to_dict() if hasattr(result, "to_dict") else result,
                         ensure_ascii=False, indent=2))
        return
    saved_metadata = None
    if arguments.command in ("resume", "inspect", "pause", "snapshot", "restore"):
        session_dir = arguments.path if (arguments.path / "session.json").is_file() else arguments.sessions_dir / arguments.path
        saved_metadata = json.loads((session_dir / "session.json").read_text(encoding="utf-8"))
        if (arguments.instruction_file or arguments.skill or arguments.hooks_file
            or arguments.mcp_config or arguments.memory_mode or arguments.memory_dir):
            parser.error("project instructions, skills, Hooks, MCP and memory settings are available when creating a session")
    elif arguments.command in ("exec", "ci", "chat", "compare-memory", "compare-memory-series", "parallel"):
        if arguments.command == "compare-memory" and arguments.memory_mode:
            parser.error("compare-memory selects all three memory modes")
        config["memory"]["mode"] = arguments.memory_mode or config["memory"]["mode"]
        config["memory_dir"] = str((arguments.memory_dir or default_memory_dir).resolve())
    elif arguments.memory_mode or arguments.memory_dir:
        parser.error("memory settings are available for repository sessions")
    if arguments.max_steps is not None:
        config["max_steps"] = arguments.max_steps
    elif arguments.command in ("exec", "ci", "chat", "compare-memory", "compare-memory-series", "parallel"):
        config["max_steps"] = config["repository_max_steps"]
    if arguments.image:
        config["sandbox"]["image"] = arguments.image
    if arguments.network:
        config["sandbox"]["network_enabled"] = True
    if arguments.instruction_file:
        config["project_instruction_files"].extend(arguments.instruction_file)
    if arguments.skill:
        config["skills"].extend(arguments.skill)
    if arguments.hooks_file:
        hooks = json.loads(arguments.hooks_file.read_text(encoding="utf-8"))
        if (type(hooks) is not dict or set(hooks) - {"before_tool", "after_tool"}
            or any(type(commands) is not list or any(type(command) is not str for command in commands)
                   for commands in hooks.values())):
            parser.error("hooks file must define lists of before_tool and after_tool commands")
        config["hooks"] = hooks
    if arguments.mcp_config:
        mcp_config = json.loads(arguments.mcp_config.read_text(encoding="utf-8"))
        if type(mcp_config) is not dict or set(mcp_config) != {"servers"} or type(mcp_config["servers"]) is not list:
            parser.error("MCP config must contain a servers list")
        config["mcp_servers"] = mcp_config["servers"]
    if arguments.recovery_mode is not None:
        config["recovery"]["enabled"] = arguments.recovery_mode == "on"
    configured_model = deepcopy(saved_metadata["config"]["model"] if saved_metadata else config["model"])
    backend = arguments.backend or configured_model["backend"]
    if backend != configured_model["backend"] and not arguments.model:
        parser.error("changing --backend requires --model")
    if backend == "anthropic":
        model_id = arguments.model or os.getenv("ANTHROPIC_MODEL") or configured_model["name"]
        base_url = arguments.base_url or os.getenv("ANTHROPIC_BASE_URL") or (
            configured_model["base_url"] if configured_model["backend"] == "anthropic"
            else "https://api.anthropic.com"
        )
        key_env = (arguments.api_key_env or
                   (configured_model.get("api_key_env") if configured_model["backend"] == "anthropic" else None)
                   or "ANTHROPIC_API_KEY")
    else:
        model_id = (arguments.model or os.getenv("DEEPSEEK_MODEL") or os.getenv("OPENAI_MODEL")
                    or configured_model["name"])
        base_url = (arguments.base_url or os.getenv("DEEPSEEK_BASE_URL")
                    or os.getenv("OPENAI_BASE_URL") or
                    (configured_model["base_url"] if configured_model["backend"] == "openai_compatible"
                     else "https://api.deepseek.com"))
        key_env = (arguments.api_key_env or
                   (configured_model.get("api_key_env") if configured_model["backend"] == "openai_compatible" else None)
                   or "DEEPSEEK_API_KEY")
    parsed_url = urlsplit(base_url)
    endpoint = f"{parsed_url.scheme}://{parsed_url.hostname}"
    if parsed_url.port is not None:
        endpoint += f":{parsed_url.port}"
    endpoint += parsed_url.path.rstrip("/")
    config["model"] = {
        "backend": backend,
        "name": model_id,
        "base_url": endpoint,
        "endpoint_host": parsed_url.hostname,
        "api_key_env": key_env,
        "max_output_tokens": arguments.max_output_tokens or configured_model.get("max_output_tokens", 4096),
    }

    def make_model():
        return create_model(config)

    if arguments.command == "run":
        result = run_task(arguments.path, make_model(), config, Path(config["results_dir"]))
        print(json.dumps({"success": result.success, "run_id": result.run_id, "stop_reason": result.stop_reason}))
        return
    if arguments.command == "batch":
        paths = sorted(path for path in arguments.path.iterdir() if (path / "task.json").is_file())
        print(json.dumps(run_batch(paths, make_model, config, Path(config["results_dir"]))))
        return
    if arguments.command == "baseline":
        if arguments.output_dir is None or arguments.repeats < 3:
            parser.error("baseline requires --output-dir and --repeats >= 3")
        if config["recovery"]["enabled"] or config["memory"]["mode"] != "off":
            parser.error("baseline requires recovery and memory to be off")
        if not os.getenv(config["model"]["api_key_env"]):
            parser.error("baseline requires the configured model API key in the environment")
        paths = sorted(path for path in arguments.path.iterdir() if (path / "task.json").is_file())
        report = run_baseline(paths, make_model, config, arguments.output_dir.resolve(), arguments.repeats)
        print(json.dumps({"status": report["status"], "run_count": report["run_count"],
                          "success_count": report["success_count"]}))
        return
    if arguments.command == "compare":
        if arguments.repeats < 1:
            parser.error("compare requires --repeats >= 1")
        paths = sorted(path for path in arguments.path.iterdir() if (path / "task.json").is_file())
        print(json.dumps(compare_batch(paths, make_model, config, Path(config["results_dir"]), arguments.repeats)))
        return
    if arguments.command == "compare-recovery":
        if arguments.output_dir is None or arguments.repeats < 3:
            parser.error("compare-recovery requires --output-dir and --repeats >= 3")
        if config["recovery"]["enabled"] or config["memory"]["mode"] != "off":
            parser.error("compare-recovery requires recovery and memory to be off in the base config")
        if not os.getenv(config["model"]["api_key_env"]):
            parser.error("compare-recovery requires the configured model API key in the environment")
        paths = sorted(path for path in arguments.path.iterdir() if (path / "task.json").is_file())
        report = run_recovery_comparison(paths, make_model, config, arguments.output_dir.resolve(), arguments.repeats)
        print(json.dumps({"status": report["status"], "run_count": report["run_count"],
                          "completed_pairs": report["completed_pairs"]}))
        return
    if arguments.command == "compare-memory":
        if not arguments.task or not arguments.check or arguments.output_dir is None:
            parser.error("compare-memory requires --task, --check and --output-dir")
        if arguments.approval_mode:
            parser.error("compare-memory uses auto approval in isolated workspaces")
        report = compare_memory(
            arguments.path, arguments.task, arguments.check, config,
            make_model, arguments.sessions_dir, arguments.output_dir.resolve(),
            arguments.repeats,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    if arguments.command == "compare-memory-series":
        if arguments.output_dir is None or arguments.approval_mode:
            parser.error("compare-memory-series requires --output-dir and uses auto approval")
        if config["recovery"]["enabled"]:
            parser.error("compare-memory-series requires recovery disabled in the base config")
        if not os.getenv(config["model"]["api_key_env"]):
            parser.error("compare-memory-series requires the configured model API key in the environment")
        report = compare_memory_series(
            arguments.path, config, arguments.output_dir.resolve(),
            arguments.sessions_dir.resolve(), make_model,
        )
        print(json.dumps({"status": report["status"], "run_count": len(report["runs"])}))
        if report["status"] != "completed":
            raise SystemExit(2)
        return
    if arguments.command == "parallel":
        if arguments.tasks_file is None or arguments.output_dir is None:
            parser.error("parallel requires --tasks-file and --output-dir")
        if arguments.approval_mode == "ask":
            parser.error("parallel requires a non-interactive approval mode")
        manifest = json.loads(arguments.tasks_file.read_text(encoding="utf-8"))
        report = run_parallel(
            arguments.path, manifest, config, make_model,
            arguments.sessions_dir, arguments.output_dir.resolve(),
            arguments.workers, arguments.approval_mode or "auto",
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if not report["integration"]["success"]:
            raise SystemExit(1)
        return

    if arguments.command in ("exec", "ci", "chat"):
        if arguments.command in ("exec", "ci") and not arguments.task:
            parser.error(f"{arguments.command} requires --task")
        if arguments.command == "ci" and (arguments.output_dir is None or arguments.approval_mode == "ask"):
            parser.error("ci requires --output-dir and a non-interactive approval mode")
        approval = arguments.approval_mode or ("ask" if arguments.command == "chat" else "auto")
        session = RepositorySession.create(
            arguments.path, arguments.sessions_dir, make_model(), config, approval
        )
    else:
        session = RepositorySession.load(session_dir, make_model(), arguments.approval_mode)
        if arguments.max_steps is not None:
            session.config["max_steps"] = arguments.max_steps
        if arguments.image:
            session.config["sandbox"]["image"] = arguments.image
        if arguments.network:
            session.config["sandbox"]["network_enabled"] = True
        if arguments.recovery_mode is not None:
            session.config["recovery"]["enabled"] = arguments.recovery_mode == "on"

    if arguments.command == "inspect":
        print(json.dumps(session.inspect(), ensure_ascii=False, indent=2))
        return
    if arguments.command == "pause":
        print(json.dumps(session.pause(), ensure_ascii=False, indent=2))
        return
    if arguments.command == "snapshot":
        commit = session.snapshot("manual")
        session.inspect()
        print(commit)
        return
    if arguments.command == "restore":
        if not arguments.snapshot:
            parser.error("restore requires --snapshot")
        print(json.dumps(session.restore(arguments.snapshot), ensure_ascii=False, indent=2))
        return
    if arguments.command in ("exec", "ci"):
        result = session.run(arguments.task, arguments.check)
        success = result["stop_reason"] == "completed" and all(
            check["status"] == "completed" and check["exit_code"] == 0
            for check in result["checks"]
        )
        if arguments.command == "ci":
            output_dir = arguments.output_dir.resolve()
            output_dir.mkdir(parents=True, exist_ok=True)
            session_dir = session.repository.session_dir
            for name in ("result.json", "trace.jsonl", "diff.patch", "status.txt"):
                copyfile(session_dir / name, output_dir / name)
            summary = {
                "success": success,
                "session_id": result["session_id"],
                "stop_reason": result["stop_reason"],
                "checks": result["checks"],
                "artifacts": ["result.json", "trace.jsonl", "diff.patch", "status.txt"],
            }
            (output_dir / "summary.json").write_text(
                json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
            )
            print(json.dumps(summary, ensure_ascii=False))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        if not success:
            raise SystemExit(1)
        return
    if arguments.command == "resume":
        if arguments.task or session.state.stop_reason not in ("completed", "verified"):
            try:
                result = session.run(arguments.task, arguments.check, arguments.resolve_pending)
            except RuntimeError as error:
                print(str(error))
                raise SystemExit(1) from error
            print(json.dumps(result, ensure_ascii=False, indent=2))
        if not arguments.interactive:
            return

    print(f"Session {session.session_id}; workspace {session.repository.workspace}")
    pending = arguments.task if arguments.command == "chat" else None
    while True:
        try:
            instruction = pending or input("task> ").strip()
        except (EOFError, KeyboardInterrupt):
            session.pause()
            print(f"Paused session {session.session_id}")
            break
        pending = None
        if instruction in ("/exit", "/quit"):
            break
        if instruction == "/pause":
            session.pause()
            print(f"Paused session {session.session_id}")
            break
        if instruction == "/status":
            print(session.repository.status(), end="")
            continue
        if instruction == "/diff":
            print(session.repository.diff(), end="")
            continue
        if instruction == "/plan":
            print(json.dumps(session.state.plan, ensure_ascii=False, indent=2))
            continue
        if instruction == "/snapshots":
            print(json.dumps(session.state.snapshots, ensure_ascii=False, indent=2))
            continue
        if instruction.startswith("/restore "):
            session.restore(instruction.split(maxsplit=1)[1])
            print("Workspace restored")
            continue
        if not instruction:
            continue
        result = session.run(instruction)
        print(result["final_message"] or result["stop_reason"])
        print(f"Diff: {result['diff_path']}")
        if result["stop_reason"] == "paused":
            break


if __name__ == "__main__":
    main()

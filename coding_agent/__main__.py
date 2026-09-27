"""Task evaluation and durable repository-session CLI."""

import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from coding_agent.eval.evaluator import compare_batch, run_batch, run_task
from coding_agent.models.openai_compatible import OpenAICompatibleBackend
from coding_agent.session.app import RepositorySession


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the coding agent")
    parser.add_argument("command", choices=[
        "run", "batch", "compare", "exec", "chat", "resume", "inspect", "pause", "snapshot", "restore",
    ])
    parser.add_argument("path", type=Path, help="Task path, Git repository, or session ID")
    parser.add_argument("--task", help="Instruction for exec, chat, or resume")
    parser.add_argument("--check", action="append", help="Project check to run after execution")
    parser.add_argument("--approval-mode", choices=["auto", "ask", "read-only"])
    parser.add_argument("--sessions-dir", type=Path, default=Path.home() / ".local/state/primuus-agent/sessions")
    parser.add_argument("--max-steps", type=int)
    parser.add_argument("--repeats", type=int, default=1, help="Runs per task and variant for compare")
    parser.add_argument("--recovery-mode", choices=["on", "off"], help="Enable or disable automatic recovery")
    parser.add_argument("--model")
    parser.add_argument("--base-url")
    parser.add_argument("--image", help="Docker image for the repository workspace")
    parser.add_argument("--network", action="store_true", help="Allow network access inside the repository container")
    parser.add_argument("--snapshot", help="Snapshot commit to restore")
    parser.add_argument("--resolve-pending", action="store_true", help="Acknowledge an interrupted tool after inspecting the workspace")
    parser.add_argument("--interactive", action="store_true", help="Stay in an interactive session after resume")
    parser.add_argument("--config", type=Path, default=Path("config/default.json"))
    arguments = parser.parse_args()
    config = json.loads(arguments.config.read_text(encoding="utf-8"))
    saved_metadata = None
    if arguments.command in ("resume", "inspect", "pause", "snapshot", "restore"):
        session_dir = arguments.path if (arguments.path / "session.json").is_file() else arguments.sessions_dir / arguments.path
        saved_metadata = json.loads((session_dir / "session.json").read_text(encoding="utf-8"))
    if arguments.max_steps is not None:
        config["max_steps"] = arguments.max_steps
    elif arguments.command in ("exec", "chat"):
        config["max_steps"] = config["repository_max_steps"]
    if arguments.image:
        config["sandbox"]["image"] = arguments.image
    if arguments.network:
        config["sandbox"]["network_enabled"] = True
    if arguments.recovery_mode is not None:
        config["recovery"]["enabled"] = arguments.recovery_mode == "on"
    model_id = (
        arguments.model or os.getenv("DEEPSEEK_MODEL") or os.getenv("OPENAI_MODEL")
        or (saved_metadata["config"]["model"]["name"] if saved_metadata else config["model"]["name"])
    )
    base_url = (
        arguments.base_url or os.getenv("DEEPSEEK_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or (saved_metadata["config"]["model"].get("base_url") if saved_metadata else None)
        or config["model"]["base_url"]
    )
    parsed_url = urlsplit(base_url)
    endpoint = f"{parsed_url.scheme}://{parsed_url.hostname}"
    if parsed_url.port is not None:
        endpoint += f":{parsed_url.port}"
    endpoint += parsed_url.path.rstrip("/")
    config["model"] = {
        "backend": "openai_compatible",
        "name": model_id,
        "base_url": endpoint,
        "endpoint_host": parsed_url.hostname,
    }

    def make_model() -> OpenAICompatibleBackend:
        return OpenAICompatibleBackend(
            model_id, base_url,
            os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY"),
        )

    if arguments.command == "run":
        result = run_task(arguments.path, make_model(), config, Path(config["results_dir"]))
        print(json.dumps({"success": result.success, "run_id": result.run_id, "stop_reason": result.stop_reason}))
        return
    if arguments.command == "batch":
        paths = sorted(path for path in arguments.path.iterdir() if (path / "task.json").is_file())
        print(json.dumps(run_batch(paths, make_model, config, Path(config["results_dir"]))))
        return
    if arguments.command == "compare":
        if arguments.repeats < 1:
            parser.error("compare requires --repeats >= 1")
        paths = sorted(path for path in arguments.path.iterdir() if (path / "task.json").is_file())
        print(json.dumps(compare_batch(paths, make_model, config, Path(config["results_dir"]), arguments.repeats)))
        return

    if arguments.command in ("exec", "chat"):
        if arguments.command == "exec" and not arguments.task:
            parser.error("exec requires --task")
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
    if arguments.command == "exec":
        result = session.run(arguments.task, arguments.check)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result["stop_reason"] != "completed" or any(
            check["status"] != "completed" or check["exit_code"] != 0
            for check in result["checks"]
        ):
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

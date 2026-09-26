"""Task evaluation and repository coding-session CLI."""

import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from coding_agent.eval.evaluator import run_batch, run_task
from coding_agent.models.openai_compatible import OpenAICompatibleBackend
from coding_agent.session.app import RepositorySession


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the coding agent")
    parser.add_argument("command", choices=["run", "batch", "exec", "chat"])
    parser.add_argument("path", type=Path, help="Task directory, tasks root, or Git repository")
    parser.add_argument("--task", help="Initial instruction for exec or chat")
    parser.add_argument("--check", action="append", default=[], help="Project check to run after exec")
    parser.add_argument("--approval-mode", choices=["auto", "ask", "read-only"])
    parser.add_argument("--sessions-dir", type=Path, default=Path.home() / ".local/state/primuus-agent/sessions")
    parser.add_argument("--max-steps", type=int)
    parser.add_argument("--model")
    parser.add_argument("--base-url")
    parser.add_argument("--config", type=Path, default=Path("config/default.json"))
    arguments = parser.parse_args()
    config = json.loads(arguments.config.read_text(encoding="utf-8"))
    if arguments.max_steps is not None:
        config["max_steps"] = arguments.max_steps
    model_id = (
        arguments.model or os.getenv("DEEPSEEK_MODEL")
        or os.getenv("OPENAI_MODEL") or config["model"]["name"]
    )
    base_url = (
        arguments.base_url or os.getenv("DEEPSEEK_BASE_URL")
        or os.getenv("OPENAI_BASE_URL") or config["model"]["base_url"]
    )
    config["model"] = {
        "backend": "openai_compatible",
        "name": model_id,
        "endpoint_host": urlsplit(base_url).hostname,
    }

    def make_model() -> OpenAICompatibleBackend:
        return OpenAICompatibleBackend(
            model_id, base_url,
            os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY"),
        )

    if arguments.command == "run":
        result = run_task(arguments.path, make_model(), config, Path(config["results_dir"]))
        print(json.dumps({"success": result.success, "run_id": result.run_id, "stop_reason": result.stop_reason}))
    elif arguments.command == "batch":
        paths = sorted(path for path in arguments.path.iterdir() if (path / "task.json").is_file())
        summary = run_batch(paths, make_model, config, Path(config["results_dir"]))
        print(json.dumps(summary))
    else:
        if arguments.command == "exec" and not arguments.task:
            parser.error("exec requires --task")
        approval = arguments.approval_mode or ("ask" if arguments.command == "chat" else "auto")
        session = RepositorySession.create(
            arguments.path, arguments.sessions_dir, make_model(), config, approval
        )
        if arguments.command == "exec":
            result = session.run(arguments.task, arguments.check)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            if result["stop_reason"] != "completed" or any(
                check["status"] != "completed" or check["exit_code"] != 0
                for check in result["checks"]
            ):
                raise SystemExit(1)
        else:
            print(f"Session {session.session_id}; workspace {session.repository.workspace}")
            pending = arguments.task
            while True:
                try:
                    instruction = pending or input("task> ").strip()
                except EOFError:
                    break
                pending = None
                if instruction in ("/exit", "/quit"):
                    break
                if instruction == "/status":
                    print(session.repository.status(), end="")
                    continue
                if instruction == "/diff":
                    print(session.repository.diff(), end="")
                    continue
                if not instruction:
                    continue
                result = session.run(instruction)
                print(result["final_message"] or result["stop_reason"])
                print(f"Diff: {result['diff_path']}")


if __name__ == "__main__":
    main()

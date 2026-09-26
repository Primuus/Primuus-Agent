"""Single-task and batch entry points for an OpenAI-compatible model."""

import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from coding_agent.eval.evaluator import run_batch, run_task
from coding_agent.models.openai_compatible import OpenAICompatibleBackend


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the coding agent")
    parser.add_argument("command", choices=["run", "batch"])
    parser.add_argument("path", type=Path, help="Task directory or tasks root")
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL"))
    parser.add_argument(
        "--base-url", default=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    )
    parser.add_argument("--config", type=Path, default=Path("config/default.json"))
    arguments = parser.parse_args()
    if not arguments.model:
        parser.error("Set --model or OPENAI_MODEL")
    config = json.loads(arguments.config.read_text(encoding="utf-8"))
    config["model"] = {
        "backend": "openai_compatible",
        "name": arguments.model,
        "endpoint_host": urlsplit(arguments.base_url).hostname,
    }
    results_dir = Path(config["results_dir"])

    def make_model() -> OpenAICompatibleBackend:
        return OpenAICompatibleBackend(
            arguments.model, arguments.base_url, os.getenv("OPENAI_API_KEY")
        )

    if arguments.command == "run":
        result = run_task(arguments.path, make_model(), config, results_dir)
        print(json.dumps({"success": result.success, "run_id": result.run_id, "stop_reason": result.stop_reason}))
    else:
        paths = sorted(path for path in arguments.path.iterdir() if (path / "task.json").is_file())
        summary = run_batch(paths, make_model, config, results_dir)
        print(json.dumps(summary))


if __name__ == "__main__":
    main()

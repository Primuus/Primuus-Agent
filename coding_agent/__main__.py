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
    parser.add_argument("--model")
    parser.add_argument("--base-url")
    parser.add_argument("--config", type=Path, default=Path("config/default.json"))
    arguments = parser.parse_args()
    config = json.loads(arguments.config.read_text(encoding="utf-8"))
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
    results_dir = Path(config["results_dir"])

    def make_model() -> OpenAICompatibleBackend:
        return OpenAICompatibleBackend(
            model_id, base_url,
            os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY"),
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

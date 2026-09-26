"""Interactive and headless work on ordinary Git repositories."""

import json
from pathlib import Path
from typing import Callable
from uuid import uuid4

from coding_agent.contracts import ToolCall
from coding_agent.models.base import ModelBackend
from coding_agent.sandbox.docker import DockerSandbox
from coding_agent.session.permissions import PermissionExecutor
from coding_agent.session.repository import RepositoryWorkspace
from coding_agent.session.runner import SessionRunner
from coding_agent.session.state import SessionSpec, SessionState
from coding_agent.tools.docker import DockerTools
from coding_agent.tools.specs import REPOSITORY_TOOL_SPECS


class RepositorySession:
    def __init__(
        self,
        repository: RepositoryWorkspace,
        model: ModelBackend,
        config: dict,
        approval_mode: str,
        ask: Callable[[str], str] = input,
    ) -> None:
        self.repository = repository
        self.model = model
        self.config = config
        self.approval_mode = approval_mode
        self.ask = ask
        self.session_id = repository.session_dir.name
        self.state = SessionState(self.session_id)

    @classmethod
    def create(
        cls,
        source: Path,
        sessions_dir: Path,
        model: ModelBackend,
        config: dict,
        approval_mode: str,
        ask: Callable[[str], str] = input,
    ) -> "RepositorySession":
        session_id = uuid4().hex[:12]
        repository = RepositoryWorkspace.create(source, sessions_dir / session_id)
        session = cls(repository, model, config, approval_mode, ask)
        session._save()
        return session

    def run(self, instruction: str, checks: list[str] | None = None) -> dict:
        sandbox_config = self.config["sandbox"]
        check_results = []
        with DockerSandbox(
            self.repository.workspace,
            sandbox_config["image"],
            sandbox_config["cpus"],
            sandbox_config["memory_mb"],
            sandbox_config["network_enabled"],
            self.config["tool_timeout_seconds"],
            persistent=True,
        ) as sandbox:
            tools = DockerTools(sandbox, self.repository.base_commit)
            permitted = PermissionExecutor(tools.execute, self.approval_mode, self.ask)
            self.state = SessionRunner(
                self.model, permitted.execute, None,
                self.config["max_steps"], self.config["task_timeout_seconds"],
                REPOSITORY_TOOL_SPECS,
            ).run(SessionSpec(self.session_id, instruction), self.state)
            for index, command in enumerate(checks or [], 1):
                result = tools.execute(ToolCall(f"check-{index}", "run_shell", {"command": command}))
                record = {
                    "command": command,
                    "status": result.status,
                    "exit_code": result.exit_code,
                    "output": result.output,
                    "error": result.error,
                }
                check_results.append(record)
                self.state.emit("project_check", record)
        return self._save(check_results)

    def _save(self, checks: list[dict] | None = None) -> dict:
        directory = self.repository.session_dir
        diff = self.repository.diff()
        status = self.repository.status()
        (directory / "diff.patch").write_text(diff, encoding="utf-8")
        (directory / "status.txt").write_text(status, encoding="utf-8")
        (directory / "trace.jsonl").write_text(
            "\n".join(json.dumps(event, ensure_ascii=False) for event in self.state.events) + "\n"
            if self.state.events else "",
            encoding="utf-8",
        )
        result = {
            "session_id": self.session_id,
            "source_repository": str(self.repository.source),
            "workspace": str(self.repository.workspace),
            "base_commit": self.repository.base_commit,
            "model_id": self.model.model_id,
            "approval_mode": self.approval_mode,
            "stop_reason": self.state.stop_reason,
            "steps": self.state.steps,
            "tool_calls": self.state.tool_calls,
            "failed_tool_calls": self.state.failed_tool_calls,
            "tokens": self.state.tokens,
            "final_message": self.state.turns[-1].response.final_message if self.state.turns else None,
            "checks": checks or [],
            "diff_path": str(directory / "diff.patch"),
            "trace_path": str(directory / "trace.jsonl"),
        }
        (directory / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return result

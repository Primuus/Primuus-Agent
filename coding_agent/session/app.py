"""Durable coding sessions on ordinary Git repositories."""

import json
from pathlib import Path
from typing import Callable
from uuid import uuid4

from coding_agent.contracts import ToolCall, ToolResult
from coding_agent.models.base import ModelBackend
from coding_agent.sandbox.docker import DockerSandbox
from coding_agent.session.journal import EventJournal, session_lock
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
        state: SessionState | None = None,
    ) -> None:
        self.repository = repository
        self.model = model
        self.config = config
        self.approval_mode = approval_mode
        self.ask = ask
        self.session_id = repository.session_dir.name
        self.journal = EventJournal(repository.session_dir / "trace.jsonl")
        self.state = state or SessionState(self.session_id)
        self.state.event_sink = self.journal.append
        last_run = max(
            (index for index, event in enumerate(self.state.events)
             if event["event_type"] in ("user_message", "session_resumed")),
            default=0,
        )
        self.last_checks = [
            event["data"] for event in self.state.events[last_run:]
            if event["event_type"] == "project_check"
        ]

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
        repository = RepositoryWorkspace.create(source, sessions_dir / uuid4().hex[:12])
        session = cls(repository, model, config, approval_mode, ask)
        (repository.session_dir / "session.json").write_text(
            json.dumps({
                "session_id": session.session_id,
                "source_repository": str(repository.source),
                "workspace": str(repository.workspace),
                "base_commit": repository.base_commit,
                "approval_mode": approval_mode,
                "config": config,
            }, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        session.state.add_snapshot(repository.base_commit, "initial")
        session._save()
        return session

    @classmethod
    def load(
        cls,
        session_dir: Path,
        model: ModelBackend,
        approval_mode: str | None = None,
        ask: Callable[[str], str] = input,
    ) -> "RepositorySession":
        with session_lock(session_dir / "session.lock"):
            metadata = json.loads((session_dir / "session.json").read_text(encoding="utf-8"))
            events = EventJournal(session_dir / "trace.jsonl").read()
        repository = RepositoryWorkspace(
            Path(metadata["source_repository"]),
            session_dir.resolve(),
            Path(metadata["workspace"]),
            metadata["base_commit"],
        )
        state = SessionState.from_events(metadata["session_id"], events)
        return cls(repository, model, metadata["config"], approval_mode or metadata["approval_mode"], ask, state)

    def run(
        self,
        instruction: str | None,
        checks: list[str] | None = None,
        resolve_pending: bool = False,
    ) -> dict:
        with session_lock(self.repository.session_dir / "session.lock"):
            self._assert_current()
            return self._run(instruction, checks, resolve_pending)

    def _run(
        self,
        instruction: str | None,
        checks: list[str] | None,
        resolve_pending: bool,
    ) -> dict:
        self.state.resolve_interrupted_turn(resolve_pending)
        last_user = max(
            (index for index, event in enumerate(self.state.events)
             if event["event_type"] == "user_message"), default=-1,
        )
        last_model = max(
            (index for index, event in enumerate(self.state.events)
             if event["event_type"] == "model_action"), default=-1,
        )
        if (instruction is None and self.state.stop_reason in (None, "paused")
            and self.state.turns and not self.state.turns[-1].response.tool_calls
            and last_model >= last_user):
            self.state.finish("completed")
            return self._save()
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
            container_name=f"coding-agent-{self.session_id}",
        ) as sandbox:
            tools = DockerTools(sandbox, self.repository.base_commit)
            permitted = PermissionExecutor(tools.execute, self.approval_mode, self.ask)

            def execute(call: ToolCall) -> ToolResult:
                if call.name != "update_plan":
                    return permitted.execute(call)
                items = call.arguments.get("items")
                if (set(call.arguments) != {"items"} or type(items) is not list
                    or any(type(item) is not dict
                           or set(item) != {"description", "status"}
                           or type(item["description"]) is not str
                           or item["status"] not in ("pending", "in_progress", "completed")
                           for item in items)):
                    return ToolResult(call.call_id, call.name, "error", "", "Invalid plan", None, 0)
                completed_before = sum(item["status"] == "completed" for item in self.state.plan)
                self.state.update_plan(items)
                if sum(item["status"] == "completed" for item in items) > completed_before:
                    self._snapshot("plan milestone")
                return ToolResult(call.call_id, call.name, "completed", "Plan updated", None, None, 0)

            try:
                self.state = SessionRunner(
                    self.model, execute, None,
                    self.config["max_steps"], self.config["task_timeout_seconds"],
                    REPOSITORY_TOOL_SPECS,
                    max_tokens=self.config.get("max_tokens"),
                    context_max_chars=self.config.get("context_max_chars"),
                    context_keep_messages=self.config.get("context_keep_messages", 12),
                ).run(SessionSpec(self.session_id, instruction), self.state)
            except KeyboardInterrupt:
                self.state.finish("paused")
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
        self._snapshot(f"after step {self.state.steps}")
        return self._save(check_results)

    def snapshot(self, label: str) -> str:
        with session_lock(self.repository.session_dir / "session.lock"):
            self._assert_current()
            return self._snapshot(label)

    def _snapshot(self, label: str) -> str:
        commit = self.repository.snapshot(label)
        self.state.add_snapshot(commit, label)
        return commit

    def restore(self, commit: str) -> dict:
        with session_lock(self.repository.session_dir / "session.lock"):
            self._assert_current()
            return self._restore(commit)

    def _restore(self, commit: str) -> dict:
        matching = [snapshot for snapshot in self.state.snapshots if snapshot["commit"] == commit]
        if not matching:
            raise ValueError("Snapshot does not belong to this session")
        self.repository.restore(commit)
        self.state.update_plan(matching[-1]["plan"])
        self.state.record_restore(commit)
        return self._save([])

    def pause(self) -> dict:
        with session_lock(self.repository.session_dir / "session.lock"):
            self._assert_current()
            self.state.finish("paused")
            return self._save()

    def inspect(self) -> dict:
        with session_lock(self.repository.session_dir / "session.lock"):
            self._assert_current()
            return self._save()

    def _assert_current(self) -> None:
        if len(self.journal.read()) != len(self.state.events):
            raise RuntimeError("Session changed in another process; reload it")

    def _save(self, checks: list[dict] | None = None) -> dict:
        if checks is not None:
            self.last_checks = checks
        directory = self.repository.session_dir
        diff = self.repository.diff()
        status = self.repository.status()
        (directory / "diff.patch").write_text(diff, encoding="utf-8")
        (directory / "status.txt").write_text(status, encoding="utf-8")
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
            "plan": self.state.plan,
            "snapshots": self.state.snapshots,
            "checks": self.last_checks,
            "diff_path": str(directory / "diff.patch"),
            "trace_path": str(directory / "trace.jsonl"),
        }
        (directory / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return result

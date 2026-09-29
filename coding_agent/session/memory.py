"""Repository-scoped memories with provenance and revision history."""

from __future__ import annotations

from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
from hashlib import sha256
from uuid import uuid4


MEMORY_KINDS = {"project", "failure", "fix"}


def repository_identity(path: Path) -> tuple[str, str]:
    root = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    commit = subprocess.run(
        ["git", "-C", root, "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    return str(Path(root).resolve()), commit


@dataclass(frozen=True)
class MemoryEntry:
    memory_id: str
    repository: str
    kind: str
    content: str
    scope: list[str]
    source: dict[str, str]
    revision: int
    active: bool
    created_at: str
    updated_at: str

    def to_dict(self) -> dict:
        return asdict(self)


class MemoryStore:
    def __init__(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = directory / "memory.sqlite3"
        with closing(self._connect()) as database, database:
            database.executescript("""
                CREATE TABLE IF NOT EXISTS memories (
                    memory_id TEXT PRIMARY KEY,
                    repository TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    source TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    active INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS memories_repository
                    ON memories(repository, active, updated_at);
                CREATE TABLE IF NOT EXISTS memory_revisions (
                    memory_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    snapshot TEXT NOT NULL,
                    PRIMARY KEY (memory_id, revision)
                );
            """)
        os.chmod(self.path, 0o600)

    def _connect(self) -> sqlite3.Connection:
        database = sqlite3.connect(self.path, timeout=30)
        database.row_factory = sqlite3.Row
        return database

    def snapshot_to(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        target = directory / "memory.sqlite3"
        with closing(self._connect()) as source, closing(sqlite3.connect(target)) as destination:
            source.backup(destination)
        os.chmod(target, 0o600)
        return target

    @staticmethod
    def _entry(row: sqlite3.Row) -> MemoryEntry:
        return MemoryEntry(
            row["memory_id"], row["repository"], row["kind"], row["content"],
            json.loads(row["scope"]), json.loads(row["source"]), row["revision"],
            bool(row["active"]), row["created_at"], row["updated_at"],
        )

    @staticmethod
    def _validate(kind: str, content: str, scope: list[str], source: dict[str, str]) -> None:
        if kind not in MEMORY_KINDS or not content.strip():
            raise ValueError("Memory needs a project, failure, or fix kind and nonempty content")
        if not source.get("kind") or not source.get("ref"):
            raise ValueError("Memory source needs kind and ref")
        if any(Path(path).is_absolute() or ".." in Path(path).parts for path in scope):
            raise ValueError("Memory scope must contain relative repository paths")

    def add(
        self, repository: str, kind: str, content: str,
        scope: list[str], source: dict[str, str], memory_id: str | None = None,
    ) -> MemoryEntry:
        self._validate(kind, content, scope, source)
        timestamp = datetime.now(timezone.utc).isoformat()
        entry = MemoryEntry(
            memory_id or uuid4().hex[:16], repository, kind, content.strip(),
            scope, source, 1, True, timestamp, timestamp,
        )
        with closing(self._connect()) as database, database:
            cursor = database.execute(
                ("INSERT OR IGNORE INTO memories VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                 if memory_id else "INSERT INTO memories VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"),
                (entry.memory_id, repository, kind, entry.content,
                 json.dumps(scope, ensure_ascii=False), json.dumps(source, ensure_ascii=False),
                 1, 1, timestamp, timestamp),
            )
            if cursor.rowcount:
                self._record(database, entry, "add")
            else:
                entry = self._entry(database.execute(
                    "SELECT * FROM memories WHERE memory_id = ?", (entry.memory_id,),
                ).fetchone())
        return entry

    def get(self, repository: str, memory_id: str) -> MemoryEntry:
        with closing(self._connect()) as database:
            row = database.execute(
                "SELECT * FROM memories WHERE repository = ? AND memory_id = ?",
                (repository, memory_id),
            ).fetchone()
        if row is None:
            raise ValueError(f"Unknown memory: {memory_id}")
        return self._entry(row)

    def list(self, repository: str, active_only: bool = True) -> list[MemoryEntry]:
        query = "SELECT * FROM memories WHERE repository = ?"
        if active_only:
            query += " AND active = 1"
        query += " ORDER BY updated_at DESC, memory_id"
        with closing(self._connect()) as database:
            rows = database.execute(query, (repository,)).fetchall()
        return [self._entry(row) for row in rows]

    def update(
        self, repository: str, memory_id: str, content: str,
        scope: list[str], source: dict[str, str],
    ) -> MemoryEntry:
        with closing(self._connect()) as database, database:
            database.execute("BEGIN IMMEDIATE")
            row = database.execute(
                "SELECT * FROM memories WHERE repository = ? AND memory_id = ?",
                (repository, memory_id),
            ).fetchone()
            if row is None:
                raise ValueError(f"Unknown memory: {memory_id}")
            previous = self._entry(row)
            self._validate(previous.kind, content, scope, source)
            timestamp = datetime.now(timezone.utc).isoformat()
            entry = MemoryEntry(
                memory_id, repository, previous.kind, content.strip(), scope, source,
                previous.revision + 1, True, previous.created_at, timestamp,
            )
            database.execute(
                "UPDATE memories SET content = ?, scope = ?, source = ?, revision = ?, active = 1, updated_at = ? "
                "WHERE repository = ? AND memory_id = ?",
                (entry.content, json.dumps(scope, ensure_ascii=False),
                 json.dumps(source, ensure_ascii=False), entry.revision,
                 timestamp, repository, memory_id),
            )
            self._record(database, entry, "update")
        return entry

    def deactivate(self, repository: str, memory_id: str) -> MemoryEntry:
        with closing(self._connect()) as database, database:
            database.execute("BEGIN IMMEDIATE")
            row = database.execute(
                "SELECT * FROM memories WHERE repository = ? AND memory_id = ?",
                (repository, memory_id),
            ).fetchone()
            if row is None:
                raise ValueError(f"Unknown memory: {memory_id}")
            previous = self._entry(row)
            timestamp = datetime.now(timezone.utc).isoformat()
            entry = MemoryEntry(
                memory_id, repository, previous.kind, previous.content, previous.scope,
                previous.source, previous.revision + 1, False, previous.created_at, timestamp,
            )
            database.execute(
                "UPDATE memories SET active = 0, revision = ?, updated_at = ? "
                "WHERE repository = ? AND memory_id = ?",
                (entry.revision, timestamp, repository, memory_id),
            )
            self._record(database, entry, "deactivate")
        return entry

    def history(self, repository: str, memory_id: str) -> list[dict]:
        self.get(repository, memory_id)
        with closing(self._connect()) as database:
            rows = database.execute(
                "SELECT revision, action, snapshot FROM memory_revisions "
                "WHERE memory_id = ? ORDER BY revision",
                (memory_id,),
            ).fetchall()
        return [{"revision": row["revision"], "action": row["action"],
                 "entry": json.loads(row["snapshot"])} for row in rows]

    @staticmethod
    def _terms(text: str) -> set[str]:
        terms: set[str] = set()
        for part in re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]+", text.lower()):
            if "\u4e00" <= part[0] <= "\u9fff" and len(part) > 1:
                terms.update(part[index:index + 2] for index in range(len(part) - 1))
            else:
                terms.add(part)
        return terms

    def select(
        self, repository: str, query: str, mode: str,
        max_entries: int, max_chars: int,
    ) -> list[dict]:
        entries = self.list(repository)
        if mode == "retrieve":
            terms = self._terms(query)
            scored = [(len(terms & self._terms(entry.content))
                       + 2 * len(terms & self._terms(" ".join(entry.scope))), entry)
                      for entry in entries]
            entries = [entry for score, entry in sorted(
                scored, key=lambda item: item[0], reverse=True,
            ) if score > 0]
        elif mode != "summary":
            raise ValueError(f"Unknown memory mode: {mode}")
        selected = []
        remaining = max_chars
        for entry in entries[:max_entries]:
            content = entry.content[:min(remaining, 1000)]
            if not content:
                break
            selected.append({
                "memory_id": entry.memory_id, "kind": entry.kind,
                "content": content, "scope": entry.scope,
                "source": entry.source, "revision": entry.revision,
            })
            remaining -= len(content)
        return selected

    def capture(
        self, repository: str, session_id: str, base_commit: str,
        instruction: str, events: list[dict], stop_reason: str,
        checks: list[dict], diff: str, changed_paths: list[str],
        trace_path: Path,
    ) -> list[MemoryEntry]:
        if stop_reason == "paused":
            return []
        failures: dict[tuple[str, str], tuple[dict, str]] = {}
        for index, event in enumerate(events):
            if event["event_type"] != "failure_detected":
                continue
            detail = event["data"]
            category = detail["category"]
            if category in ("model_service", "permission"):
                continue
            output = ""
            if detail.get("source") == "project_check":
                check = next((prior["data"] for prior in reversed(events[:index])
                              if prior["event_type"] == "project_check"), None)
                if check:
                    output = check.get("error") or check.get("output") or ""
            else:
                result = next((later["data"] for later in events[index + 1:]
                               if later["event_type"] == "tool_result"
                               and later["step"] == event["step"]
                               and later["data"]["name"] == detail.get("tool")), None)
                if result:
                    output = result.get("error") or result.get("output") or ""
            key = (category, detail.get("tool", detail.get("source", "")))
            failures[key] = (event, output[:500])

        captured = []
        for event, output in list(failures.values())[-3:]:
            detail = event["data"]
            content = (
                f"Task: {instruction[:300]}\nFailure: {detail['category']}"
                f" in {detail.get('tool', detail.get('source', 'session'))}; "
                f"status={detail.get('status', 'failed')}, exit={detail.get('exit_code')}.\n"
                f"Observed: {output}\nFinal outcome: {stop_reason}."
            )
            source = {
                "kind": "session_trace", "ref": str(trace_path),
                "session_id": session_id, "event": event["timestamp"],
                "commit": base_commit,
            }
            digest = sha256(f"{repository}:{session_id}:failure:{event['timestamp']}".encode()).hexdigest()[:16]
            captured.append(self.add(repository, "failure", content, changed_paths, source, digest))

        checks_passed = bool(checks) and all(
            check["status"] == "completed" and check["exit_code"] == 0 for check in checks
        )
        if checks_passed:
            commands = [check["command"] for check in checks]
            content = (
                "Project checks observed to pass on one session workspace:\n"
                + "\n".join(commands)
                + "\nRerun on the current revision; this does not establish task completion."
            )
            source = {
                "kind": "project_check", "ref": str(trace_path),
                "session_id": session_id, "event": "passed", "commit": base_commit,
            }
            digest = sha256(json.dumps(
                [repository, base_commit, commands], ensure_ascii=False,
            ).encode()).hexdigest()[:16]
            entry = self.add(repository, "project", content, [], source, digest)
            if entry.source["session_id"] == session_id:
                captured.append(entry)

        if stop_reason == "completed" and checks_passed and diff:
            final = next((event["data"]["response"]["final_message"] for event in reversed(events)
                          if event["event_type"] == "model_action"
                          and event["data"]["response"]["final_message"]), "")
            content = (
                f"Task: {instruction[:300]}\nResult: {final[:400]}\n"
                f"Changed paths: {', '.join(changed_paths)}\n"
                f"Passed checks: {', '.join(check['command'] for check in checks)}\n"
                f"Patch excerpt:\n{diff[:1200]}"
            )
            source = {
                "kind": "verified_session", "ref": str(trace_path),
                "session_id": session_id, "event": "completed",
                "commit": base_commit, "diff_sha256": sha256(diff.encode()).hexdigest(),
            }
            digest = sha256(f"{repository}:{session_id}:fix".encode()).hexdigest()[:16]
            captured.append(self.add(repository, "fix", content, changed_paths, source, digest))
        return captured

    @staticmethod
    def _record(database: sqlite3.Connection, entry: MemoryEntry, action: str) -> None:
        database.execute(
            "INSERT INTO memory_revisions VALUES (?, ?, ?, ?)",
            (entry.memory_id, entry.revision, action,
             json.dumps(entry.to_dict(), ensure_ascii=False)),
        )

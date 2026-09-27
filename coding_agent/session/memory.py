"""Repository-scoped memories with provenance and revision history."""

from __future__ import annotations

from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import subprocess
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
            database.execute(
                "INSERT INTO memories VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (entry.memory_id, repository, kind, entry.content,
                 json.dumps(scope, ensure_ascii=False), json.dumps(source, ensure_ascii=False),
                 1, 1, timestamp, timestamp),
            )
            self._record(database, entry, "add")
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
    def _record(database: sqlite3.Connection, entry: MemoryEntry, action: str) -> None:
        database.execute(
            "INSERT INTO memory_revisions VALUES (?, ?, ?, ?)",
            (entry.memory_id, entry.revision, action,
             json.dumps(entry.to_dict(), ensure_ascii=False)),
        )

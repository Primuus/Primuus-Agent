"""Append-only session events, flushed before the next action begins."""

import json
import os
from contextlib import contextmanager
import fcntl
from pathlib import Path
from typing import Any, Iterator


@contextmanager
def session_lock(path: Path) -> Iterator[None]:
    with path.open("a") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("This session is already active in another process") from error
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class EventJournal:
    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, event: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        content = self.path.read_bytes()
        if not content.endswith(b"\n"):
            content = content[:content.rfind(b"\n") + 1]
            with self.path.open("r+b") as stream:
                stream.truncate(len(content))
                stream.flush()
                os.fsync(stream.fileno())
        return [json.loads(line) for line in content.decode("utf-8").splitlines()]

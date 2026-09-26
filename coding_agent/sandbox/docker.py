"""A fresh, resource-limited Docker workspace for each task run."""

import os
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4


class DockerSandbox:
    def __init__(
        self,
        repository: Path,
        image: str,
        cpus: float,
        memory_mb: int,
        network_enabled: bool,
        tool_timeout_seconds: int,
        persistent: bool = False,
    ) -> None:
        self.repository = repository
        self.image = image
        self.cpus = cpus
        self.memory_mb = memory_mb
        self.network_enabled = network_enabled
        self.tool_timeout_seconds = tool_timeout_seconds
        self.persistent = persistent
        self.container_name = f"coding-agent-{uuid4().hex[:12]}"
        self._temporary: TemporaryDirectory[str] | None = None
        self.workspace: Path | None = None

    def __enter__(self) -> "DockerSandbox":
        if self.persistent:
            self.workspace = self.repository
        else:
            self._temporary = TemporaryDirectory(prefix="coding-agent-")
            self.workspace = Path(self._temporary.name) / "workspace"
            shutil.copytree(self.repository, self.workspace)
        command = [
            "docker", "run", "--detach", "--rm",
            "--name", self.container_name,
            "--cpus", str(self.cpus),
            "--memory", f"{self.memory_mb}m",
            "--pids-limit", "64",
            "--read-only",
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--network", "bridge" if self.network_enabled else "none",
            "--user", f"{os.getuid()}:{os.getgid()}",
            "--volume", f"{self.workspace}:/workspace:rw",
            "--workdir", "/workspace",
            self.image,
            "sleep", "infinity",
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError:
            if self._temporary is not None:
                self._temporary.cleanup()
            raise
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        subprocess.run(
            ["docker", "rm", "--force", self.container_name],
            capture_output=True,
            check=True,
        )
        if self._temporary is not None:
            self._temporary.cleanup()

    def exec(
        self, command: list[str], input_text: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        docker_command = ["docker", "exec"]
        if input_text is not None:
            docker_command.append("--interactive")
        docker_command.extend([self.container_name, *command])
        return subprocess.run(
            docker_command,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=self.tool_timeout_seconds + 2,
        )

    def relative_path(self, path: str) -> str:
        supplied = Path(path)
        if supplied.is_absolute() or ".." in supplied.parts:
            raise ValueError("Path must stay inside /workspace")
        resolved = (self.workspace / supplied).resolve()
        if not resolved.is_relative_to(self.workspace.resolve()):
            raise ValueError("Path must stay inside /workspace")
        return str(supplied)

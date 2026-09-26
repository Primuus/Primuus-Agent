"""Run a task's private verifier against a disposable workspace snapshot."""

import os
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic

from coding_agent.contracts import VerificationResult
from coding_agent.harness.task import LoadedTask
from coding_agent.verifier.base import VerifierError


class DockerVerifier:
    def __init__(
        self,
        task: LoadedTask,
        workspace: Path,
        image: str,
        cpus: float,
        memory_mb: int,
        timeout_seconds: int,
    ) -> None:
        self.task = task
        self.workspace = workspace
        self.image = image
        self.cpus = cpus
        self.memory_mb = memory_mb
        self.timeout_seconds = timeout_seconds

    def check(self) -> VerificationResult:
        started = monotonic()
        with TemporaryDirectory(prefix="coding-verifier-") as temporary:
            root = Path(temporary)
            snapshot = root / "workspace"
            verifier_dir = root / "verifier"
            shutil.copytree(self.workspace, snapshot, symlinks=True)
            verifier_dir.mkdir()
            verifier_path = verifier_dir / self.task.spec.verifier.entrypoint
            verifier_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.task.verifier, verifier_path)
            command = [
                "docker", "run", "--rm",
                "--network", "none",
                "--cpus", str(self.cpus),
                "--memory", f"{self.memory_mb}m",
                "--pids-limit", "64",
                "--read-only",
                "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m",
                "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges",
                "--user", f"{os.getuid()}:{os.getgid()}",
                "--env", "PYTHONDONTWRITEBYTECODE=1",
                "--volume", f"{snapshot}:/workspace:rw",
                "--volume", f"{verifier_dir}:/verifier:ro",
                "--workdir", "/workspace",
                self.image,
                "timeout", "--kill-after=1s", f"{self.timeout_seconds}s",
                "python", f"/verifier/{self.task.spec.verifier.entrypoint}",
            ]
            try:
                completed = subprocess.run(
                    command, capture_output=True, text=True,
                    timeout=self.timeout_seconds + 2,
                )
            except subprocess.TimeoutExpired as error:
                raise VerifierError("Verifier timed out") from error
        if completed.returncode == 124:
            raise VerifierError("Verifier timed out")
        return VerificationResult(
            passed=completed.returncode == 0,
            output=completed.stdout,
            error=completed.stderr or None,
            exit_code=completed.returncode,
            duration_ms=int((monotonic() - started) * 1000),
        )

"""Private verifier for task_001; run with cwd set to the task workspace."""

from pathlib import Path
import sys


sys.path.insert(0, str(Path.cwd()))

from calculator import add  # noqa: E402


assert add(2, 3) == 5
assert add(-2, 3) == 1
print("task_001 passed")

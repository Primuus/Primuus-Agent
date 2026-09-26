import subprocess
import sys

for name in ("Ada", "Lin"):
    result = subprocess.run(
        [sys.executable, "greet.py", name], capture_output=True, text=True, check=True
    )
    assert result.stdout == f"Hello, {name}!\n"

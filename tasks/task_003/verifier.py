from pathlib import Path
import sys

sys.path.insert(0, str(Path.cwd()))
from report import render

assert render(3) == "Result: 6"
assert render(-2) == "Result: -4"

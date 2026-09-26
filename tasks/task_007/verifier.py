from pathlib import Path
import sys

sys.path.insert(0, str(Path.cwd()))
from ratio import ratio

assert ratio(10, 0) == 0.0
assert ratio(10, 2) == 5.0
assert ratio(-3, 2) == -1.5

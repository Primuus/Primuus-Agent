from pathlib import Path
import sys

sys.path.insert(0, str(Path.cwd()))
from sequence import first_even

assert first_even([1, 5, 8, 2]) == 8
assert first_even([1, 3, 5]) is None
assert first_even([]) is None
assert first_even([0, 2]) == 0

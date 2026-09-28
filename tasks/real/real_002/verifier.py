import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "src"))
import humanize

for exponent, unit in [(24, "septillion"), (27, "octillion"), (30, "nonillion"), (33, "decillion")]:
    assert humanize.intword(10**exponent - 1) == f"1.0 {unit}"
    assert humanize.intword(10**exponent - 1, "%.0f") == f"1 {unit}"
assert humanize.intword(10**36) == "1000.0 decillion"
assert humanize.intword(2 * 10**100) == "2.0 googol"

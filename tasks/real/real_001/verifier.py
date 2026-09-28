import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "src"))
import humanize

assert humanize.natural_list(iter(())) == ""
assert humanize.natural_list(("one",)) == "one"
assert humanize.natural_list(("one", "two")) == "one and two"
assert humanize.natural_list((item for item in ["one", "two", "three"])) == "one, two and three"
assert humanize.natural_list({"one": 1, "two": 2}.keys()) == "one and two"
assert humanize.natural_list(range(1, 4)) == "1, 2 and 3"
assert humanize.natural_list([1, "two"]) == "1 and two"

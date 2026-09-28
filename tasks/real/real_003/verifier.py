import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "src"))
import humanize

value = 10**400 + 123
assert humanize.intcomma(value) == f"{value:,}"
assert humanize.intcomma(-value) == f"{-value:,}"
assert humanize.intcomma(1234567) == "1,234,567"

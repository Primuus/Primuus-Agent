from pathlib import Path
import sys

sys.path.insert(0, str(Path.cwd()))
from text_utils import normalize_name

assert normalize_name("  Ada   Lovelace ") == "ada-lovelace"
assert normalize_name("Grace\tHopper") == "grace-hopper"
assert normalize_name("Lin") == "lin"

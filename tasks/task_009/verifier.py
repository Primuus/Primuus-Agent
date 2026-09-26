from pathlib import Path
import sys

sys.path.insert(0, str(Path.cwd()))
from config_parser import parse

assert parse("  host = localhost\n# comment\n\n token = a=b=c\n") == {
    "host": "localhost", "token": "a=b=c"
}
assert parse("x=1\ny=2") == {"x": "1", "y": "2"}

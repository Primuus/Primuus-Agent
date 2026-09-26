import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path.cwd()))
with TemporaryDirectory() as directory:
    os.chdir(directory)
    from lookup import words

    assert words() == ["alpha", "beta", "gamma"]

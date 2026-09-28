import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "src"))
from packaging.markers import InvalidMarker, Marker
from packaging.requirements import InvalidRequirement, Requirement

for suffix in ("\n", "\r", "\r\n"):
    for value in ("demo>=1", 'demo; python_version >= "3"'):
        try:
            Requirement(value + suffix)
        except InvalidRequirement:
            pass
        else:
            raise AssertionError((value, suffix))
    try:
        Marker('python_version >= "3"' + suffix)
    except InvalidMarker:
        pass
    else:
        raise AssertionError(suffix)
assert Requirement("demo>=1 \t") == Requirement("demo>=1")
assert Marker('python_version >= "3" \t') == Marker('python_version >= "3"')

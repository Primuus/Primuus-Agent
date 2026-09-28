import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "src"))
from packaging._parser import Value
from packaging.markers import Marker
from packaging.requirements import Requirement

assert Value('a"b').serialize() == "'a\"b'"
assert Value("a'b").serialize() == '"a\'b"'
try:
    Value('a"b\'c').serialize()
except ValueError:
    pass
else:
    raise AssertionError("ambiguous value was serialized")
source = 'demo; \'a" == os_name or python_version >= "0" or "b\' == os_name'
requirement = Requirement(source)
assert str(requirement) == source
assert Requirement(str(requirement)).marker == requirement.marker
assert str(Marker("'a\"' == os_name")) == "'a\"' == os_name"

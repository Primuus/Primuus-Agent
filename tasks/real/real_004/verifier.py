import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "src"))
from packaging import tags

assert list(tags.cpython_tags((3, 11), abis=["abi"], platforms=[])) == []
assert list(tags.generic_tags("demo", ["abi"], iter(()))) == []
assert list(tags.compatible_tags((3,), "cp3", [])) == [
    tags.Tag("cp3", "none", "any"), tags.Tag("py3", "none", "any")
]
assert tags.Tag("demo", "abi", "custom") in list(tags.generic_tags("demo", ["abi"], ["custom"]))

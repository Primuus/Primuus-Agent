import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
from boltons.listutils import BarrelList
from boltons.setutils import IndexedSet

items = BarrelList(range(30000))
items.pop(0)
items.insert(0, 0)
assert len(items.lists) > 1
try:
    items[len(items)]
except IndexError:
    pass
else:
    raise AssertionError("out-of-bounds index returned a value")
items.insert(len(items), "end")
assert items[-1] == "end"
items.insert(len(items) + 20, "past end")
assert items[-1] == "past end"
items.insert(-len(items) - 20, "start")
assert items[0] == "start"
for _ in range(len(items.lists[-1])):
    items.pop(len(items) - 1)
expected = items[-1]
assert items.pop() == expected

indexed = IndexedSet(range(1000))
indexed.difference_update(set(range(0, 1000, 2)))
assert list(indexed) == list(range(1, 1000, 2))
assert indexed.index(501) == 250
indexed.add(0)
assert indexed[-1] == 0
indexed = IndexedSet(range(1000))
indexed.intersection_update(set(range(500, 2000)))
assert list(indexed) == list(range(500, 1000))

compactions = []
original = IndexedSet._compact
def count_compaction(self):
    compactions.append(1)
    return original(self)
IndexedSet._compact = count_compaction
try:
    indexed = IndexedSet(range(5000))
    indexed.difference_update(set(range(0, 5000, 2)))
    assert list(indexed) == list(range(1, 5000, 2))
    assert len(compactions) <= 1
finally:
    IndexedSet._compact = original

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
from boltons.jsonutils import JSONLIterator


class CappedReader:
    def __init__(self, text):
        self.stream = io.StringIO(text)
        self.reads = 0

    def read(self, size=-1):
        self.reads += 1
        if self.reads > 10:
            raise AssertionError("read after EOF")
        return self.stream.read(size)

    def __iter__(self):
        return iter(self.stream)

    def __getattr__(self, name):
        return getattr(self.stream, name)


text = '{"one": 1}\n{"two": 2}'
assert list(JSONLIterator(io.StringIO(text))) == [{"one": 1}, {"two": 2}]
assert list(JSONLIterator(CappedReader(text), rel_seek=0.9)) == []
assert list(JSONLIterator(CappedReader(text), rel_seek=-0.5)) == list(
    JSONLIterator(CappedReader(text), rel_seek=0.5)
)

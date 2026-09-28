import io
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
from boltons.ioutils import SpooledBytesIO, SpooledStringIO

for rolled in (False, True):
    with SpooledBytesIO() as stream:
        if rolled:
            stream.rollover()
        assert stream.write(bytearray(b"abc")) == 3
        assert stream.write(b"") == 0
        assert stream.getvalue() == b"abc"

    with SpooledBytesIO(max_size=4) as stream:
        with memoryview(bytearray(b"abcd")).cast("I") as view:
            assert stream.write(view) == 4
        assert stream.getvalue() == b"abcd"

    stream = SpooledBytesIO()
    if rolled:
        stream.rollover()
    writer = io.BufferedWriter(stream)
    writer.write(b"payload")
    writer.flush()
    assert stream.getvalue() == b"payload"
    writer.close()

    with SpooledStringIO() as stream:
        assert stream.write("a☃bc") == 4
        if rolled:
            stream.rollover()
        stream.seek(3)
        assert stream.seek(-2, os.SEEK_CUR) == 1
        assert stream.read(2) == "☃b"
        assert stream.tell() == 3
        try:
            stream.seek(-5, os.SEEK_CUR)
        except ValueError:
            pass
        else:
            raise AssertionError("negative destination accepted")
        assert stream.tell() == 3

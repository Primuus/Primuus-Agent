import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
from boltons.statsutils import Stats

for data in ([5] * 10, [0] * 10 + [100]):
    stats = Stats(data)
    assert stats.get_histogram_counts() == [(float(min(data)), len(data))]
    assert stats.format_histogram()

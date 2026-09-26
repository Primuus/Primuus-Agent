from pathlib import Path


def words():
    return [line for line in Path("data.txt").read_text().splitlines() if line]

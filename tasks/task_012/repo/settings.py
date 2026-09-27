import json
from pathlib import Path


def load_settings(path):
    settings = json.loads(Path(path).read_text(encoding="utf-8"))
    settings["delimiter"] = ","
    return settings

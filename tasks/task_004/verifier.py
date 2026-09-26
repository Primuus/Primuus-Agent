import json
from pathlib import Path

settings = json.loads(Path("settings.json").read_text())
assert settings["host"] == "127.0.0.1"
assert type(settings["port"]) is int and settings["port"] == 8080
assert settings["debug"] is False

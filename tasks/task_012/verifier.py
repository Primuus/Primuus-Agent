import csv
from io import StringIO
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path.cwd()))
from app import export_customers

rows = [{"id": 1, "name": "Ada; Lovelace"}, {"id": 2, "name": 'Lin "N"'}]
output = export_customers(rows, Path.cwd() / "export.json")
assert list(csv.reader(StringIO(output), delimiter=";")) == [
    ["id", "name"], ["1", "Ada; Lovelace"], ["2", 'Lin "N"'],
]
assert '"Ada; Lovelace"' in output

with TemporaryDirectory() as directory:
    config = Path(directory) / "other.json"
    config.write_text('{"delimiter": "|", "include_header": false, "columns": ["name", "id"]}', encoding="utf-8")
    other = export_customers(rows, config)
    assert list(csv.reader(StringIO(other), delimiter="|")) == [
        ["Ada; Lovelace", "1"], ['Lin "N"', "2"],
    ]

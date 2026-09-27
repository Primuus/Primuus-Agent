from pathlib import Path
import sys

sys.path.insert(0, str(Path.cwd()))
from api import get_cases

records = [
    {"id": 1, "status": "Open"},
    {"id": 2, "status": "closed"},
    {"id": 3, "status": " OPEN "},
    {"id": 4, "status": "open"},
    {"id": 5, "status": "Closed"},
]
assert get_cases(records, " open ", 1, 2) == {"total": 3, "items": [records[0], records[2]]}
assert get_cases(records, "OPEN", 2, 2) == {"total": 3, "items": [records[3]]}
assert get_cases(records, "closed", 1, 1) == {"total": 2, "items": [records[1]]}
assert records[2]["status"] == " OPEN "

from pathlib import Path
import sys

sys.path.insert(0, str(Path.cwd()))
from user_api import find_user

users = [{"id": 1, "name": "Ada"}, {"id": 2, "name": "Lin"}]
assert find_user(users, 2) == users[1]
assert find_user(users, 3) is None
assert find_user([], 1) is None
assert users == [{"id": 1, "name": "Ada"}, {"id": 2, "name": "Lin"}]

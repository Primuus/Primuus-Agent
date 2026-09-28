# Terminate JSONL iteration at EOF and fix relative seek

`boltons.jsonutils.JSONLIterator` can repeatedly read after EOF when a relative seek lands inside the final line of a file without a trailing newline. A negative `rel_seek` should mean an offset measured backward from the end, so `-0.5` should select the same tail as `0.5`. Fix both behaviors without changing ordinary forward iteration.

Repository check: `python -m pytest -q tests/test_jsonutils.py`

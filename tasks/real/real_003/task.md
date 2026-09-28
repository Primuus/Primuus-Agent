# Format very large integers with intcomma

`humanize.intcomma` raises an overflow error when given a Python integer larger than the floating point range. It must format arbitrarily large positive and negative integers with comma grouping, while preserving ordinary integer formatting.

Repository check: `PYTHONPATH=src python -m pytest -q tests/test_number.py`

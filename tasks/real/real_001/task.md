# Accept general iterables in natural_list

`humanize.natural_list` currently expects indexable lists. Make it accept any finite iterable, including tuples, generators, mapping key views, and ranges. Preserve the existing wording for zero, one, two, and three or more items, and stringify each item once.

Repository check: `PYTHONPATH=src python -m pytest -q tests/test_lists.py`

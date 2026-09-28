# Preserve explicitly empty platform iterables

In `packaging.tags`, an explicitly empty `platforms` iterable means no platform-specific tags. Apply this consistently to `cpython_tags`, `generic_tags`, and `compatible_tags`. `compatible_tags` should still produce its platform-independent `any` tags. Omitted `platforms` should continue using detected platform tags.

Repository check: `PYTHONPATH=src python -m pytest -q tests/test_tags.py`

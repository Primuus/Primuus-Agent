# Reject trailing line breaks in parsed requirements

The requirement and marker parsers accept a final line break because their end-of-input rule matches before a trailing newline. A requirement or marker ending in `\n`, `\r`, or `\r\n` must be rejected as invalid input. Trailing horizontal spaces and tabs remain valid.

Repository check: `PYTHONPATH=src python -m pytest -q tests/test_requirements.py tests/test_markers.py`
